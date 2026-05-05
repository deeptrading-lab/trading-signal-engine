"""
SDK 세션 라이프사이클 관리 (Dev Manager 자연어 분기).

PRD: docs/prd/dev-relay-natural-language.md §3.3

- Slack `thread_ts` 1:1 SDK `session_id` 매핑.
- `~/.local/state/dev_relay/queue.db` 의 신규 테이블 `agent_sessions` 사용
  (queue 와 같은 SQLite 파일 — 백업·권한 정책 단일화).
- UNIQUE(thread_ts, channel_id) 제약 — 같은 스레드의 두 번째 row 가 들어오지 않게.
- 만료 정책 (마지막 활동 후 30분 경과) 시 같은 row 의 `session_id` 가 갱신된다
  (PRD §3.3 / AC-8 — "갱신되어도 무방").

본 모듈은 stateless API 만 노출하며 connection 은 매 호출마다 열고 닫는다.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

from ai.dev_relay.queue import default_db_path

KST = timezone(timedelta(hours=9), name="KST")

# PRD §3.3 — 세션 만료 30분.
SESSION_IDLE_TIMEOUT = timedelta(minutes=30)

# 모델 라벨 enum (자유 문자열).
MODEL_HAIKU = "haiku-4-5"
MODEL_SONNET = "sonnet-4-6"
MODEL_MIXED = "mixed"


_SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_ts       TEXT NOT NULL,
    channel_id      TEXT NOT NULL,
    session_id      TEXT NOT NULL,
    started_at      TEXT NOT NULL,
    last_active_at  TEXT NOT NULL,
    model_used      TEXT NOT NULL,
    turn_count      INTEGER NOT NULL DEFAULT 1,
    UNIQUE(thread_ts, channel_id)
);
CREATE INDEX IF NOT EXISTS idx_agent_sessions_last_active
    ON agent_sessions(last_active_at);
"""


@dataclass(frozen=True, slots=True)
class AgentSession:
    """agent_sessions row 의 immutable 표현."""

    id: int
    thread_ts: str
    channel_id: str
    session_id: str
    started_at: str
    last_active_at: str
    model_used: str
    turn_count: int


def _now_kst_iso() -> str:
    return datetime.now(tz=KST).isoformat(timespec="seconds")


def _parse_iso(text: str) -> datetime:
    """ISO-8601 (KST) 문자열을 aware datetime 으로 파싱."""
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=KST)
    return dt


class AgentSessionStore:
    """SDK 세션 메타데이터 SQLite 저장소.

    - DB 파일은 queue 와 공유 (`default_db_path()`).
    - 호출은 stateless — 매 메서드가 connection 을 열고 닫는다.
    """

    def __init__(self, db_path: Path | str | None = None) -> None:
        self._db_path = Path(db_path) if db_path is not None else default_db_path()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @property
    def db_path(self) -> Path:
        return self._db_path

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._db_path, isolation_level=None, timeout=10.0)
        try:
            conn.row_factory = sqlite3.Row
            yield conn
        finally:
            conn.close()

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    # ------------------------------------------------------------------
    # 조회
    # ------------------------------------------------------------------
    def get(self, *, thread_ts: str, channel_id: str) -> AgentSession | None:
        if not thread_ts or not channel_id:
            return None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM agent_sessions "
                "WHERE thread_ts = ? AND channel_id = ?",
                (thread_ts, channel_id),
            ).fetchone()
        return _row_to_session(row) if row is not None else None

    # ------------------------------------------------------------------
    # 생성 / 갱신 (UPSERT)
    # ------------------------------------------------------------------
    def start(
        self,
        *,
        thread_ts: str,
        channel_id: str,
        session_id: str,
        model_used: str,
    ) -> AgentSession:
        """신규 세션 row 를 생성하거나, 같은 thread 의 row 를 신규 session_id 로
        갱신한다 (만료 후 재시작 경로).

        UNIQUE(thread_ts, channel_id) 제약 때문에 INSERT 실패 시 기존 row 를
        업데이트해 turn_count 를 1 로 리셋한다.
        """
        if not thread_ts or not channel_id or not session_id:
            raise ValueError("thread_ts/channel_id/session_id 가 비어 있습니다.")

        now = _now_kst_iso()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT id FROM agent_sessions "
                "WHERE thread_ts = ? AND channel_id = ?",
                (thread_ts, channel_id),
            ).fetchone()
            if existing is None:
                conn.execute(
                    """
                    INSERT INTO agent_sessions (
                        thread_ts, channel_id, session_id,
                        started_at, last_active_at, model_used, turn_count
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (thread_ts, channel_id, session_id, now, now, model_used, 1),
                )
            else:
                conn.execute(
                    """
                    UPDATE agent_sessions
                       SET session_id = ?,
                           started_at = ?,
                           last_active_at = ?,
                           model_used = ?,
                           turn_count = 1
                     WHERE id = ?
                    """,
                    (session_id, now, now, model_used, int(existing["id"])),
                )
            conn.execute("COMMIT")

        result = self.get(thread_ts=thread_ts, channel_id=channel_id)
        assert result is not None
        return result

    def resume(
        self,
        *,
        thread_ts: str,
        channel_id: str,
        model_used: str | None = None,
    ) -> AgentSession | None:
        """기존 세션의 turn_count 를 +1 하고 last_active_at 갱신.

        반환 값이 None 이면 row 가 없거나 호출 측이 신규 세션을 시작해야 한다.
        만료 판정은 호출 측 (`is_expired`) 책임.
        """
        if not thread_ts or not channel_id:
            return None
        now = _now_kst_iso()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM agent_sessions "
                "WHERE thread_ts = ? AND channel_id = ?",
                (thread_ts, channel_id),
            ).fetchone()
            if row is None:
                conn.execute("COMMIT")
                return None
            new_model = model_used if model_used else row["model_used"]
            # 모델이 바뀌면 mixed 로 표기 (Haiku 분류 → Sonnet 본응답 시).
            if model_used and row["model_used"] != model_used:
                new_model = MODEL_MIXED
            conn.execute(
                """
                UPDATE agent_sessions
                   SET last_active_at = ?,
                       model_used = ?,
                       turn_count = turn_count + 1
                 WHERE id = ?
                """,
                (now, new_model, int(row["id"])),
            )
            conn.execute("COMMIT")

        return self.get(thread_ts=thread_ts, channel_id=channel_id)


def is_expired(
    session: AgentSession,
    *,
    now: datetime | None = None,
    timeout: timedelta = SESSION_IDLE_TIMEOUT,
) -> bool:
    """세션의 마지막 활동 시각이 timeout 을 초과했는지 (PRD §3.3 / AC-8).

    `now` 가 None 이면 현재 KST 시각을 사용. 단위 테스트에서는 명시적으로
    주입한다.
    """
    last_active = _parse_iso(session.last_active_at)
    current = now if now is not None else datetime.now(tz=KST)
    if current.tzinfo is None:
        current = current.replace(tzinfo=KST)
    return (current - last_active) > timeout


def _row_to_session(row: sqlite3.Row | None) -> AgentSession:
    assert row is not None
    return AgentSession(
        id=int(row["id"]),
        thread_ts=row["thread_ts"],
        channel_id=row["channel_id"],
        session_id=row["session_id"],
        started_at=row["started_at"],
        last_active_at=row["last_active_at"],
        model_used=row["model_used"],
        turn_count=int(row["turn_count"]),
    )


__all__ = [
    "AgentSession",
    "AgentSessionStore",
    "SESSION_IDLE_TIMEOUT",
    "MODEL_HAIKU",
    "MODEL_SONNET",
    "MODEL_MIXED",
    "is_expired",
]
