"""
SQLite 기반 작업 큐 (Dev Relay).

PRD §3.4 / AC-11 / AC-14:
- 백엔드: SQLite 단일 파일 (`${XDG_STATE_HOME:-~/.local/state}/dev_relay/queue.db`).
- 디렉토리 권한 0700, 파일 권한 0600.
- 멱등성: `idempotency_key`(Slack `client_msg_id` 또는 `event_id`) UNIQUE.
- 동시 실행 제한: 1건. 추가 명령은 `pending` 으로 적재.
- 재시작 복구: `running` 잔존 row 는 `failed` 로 마킹.

본 모듈은 stateless API 만 노출하며 connection 은 매 호출마다 열고 닫는다.
세션 동안 한 줄 락이 필요하면 `BEGIN IMMEDIATE` 트랜잭션으로 직렬화한다.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

KST = timezone(timedelta(hours=9), name="KST")

# 작업 상태 enum (TEXT 컬럼 단순화).
STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"

_VALID_STATUSES: frozenset[str] = frozenset(
    {STATUS_PENDING, STATUS_RUNNING, STATUS_DONE, STATUS_FAILED, STATUS_CANCELLED}
)

# PRD §3.4 — 스키마는 변경 없이 그대로 유지.
_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    idempotency_key TEXT NOT NULL UNIQUE,
    user_id         TEXT NOT NULL,
    command         TEXT NOT NULL,
    status          TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    started_at      TEXT,
    finished_at     TEXT,
    result_summary  TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at);
"""


@dataclass(frozen=True, slots=True)
class Job:
    """작업 큐 row 의 immutable 표현."""

    id: int
    idempotency_key: str
    user_id: str
    command: str
    status: str
    created_at: str
    started_at: str | None
    finished_at: str | None
    result_summary: str | None


def default_db_path() -> Path:
    """PRD §3.4 의 디폴트 위치를 반환.

    `XDG_STATE_HOME` 우선, 없으면 `~/.local/state/dev_relay/queue.db`.
    """
    xdg_state = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(xdg_state) / "dev_relay" / "queue.db"


def _now_kst_iso() -> str:
    return datetime.now(tz=KST).isoformat(timespec="seconds")


def _ensure_dir_secure(path: Path) -> None:
    """부모 디렉토리를 만들고 권한 0700 으로 보장 (PRD §3.8)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, 0o700)
    except (PermissionError, OSError):
        # macOS/Linux 외 환경에서는 best-effort.
        pass


def _ensure_file_secure(path: Path) -> None:
    """파일 권한 0600 으로 보장."""
    if path.exists():
        try:
            os.chmod(path, 0o600)
        except (PermissionError, OSError):
            pass


class JobQueue:
    """SQLite 작업 큐.

    인스턴스는 DB 경로만 소유하며, connection 은 호출마다 열고 닫는다.
    동시성은 SQLite 의 트랜잭션과 UNIQUE 제약으로 직렬화된다.
    """

    def __init__(self, db_path: Path | str | None = None) -> None:
        self._db_path = Path(db_path) if db_path is not None else default_db_path()
        _ensure_dir_secure(self._db_path)
        self._initialize()
        _ensure_file_secure(self._db_path)

    @property
    def db_path(self) -> Path:
        return self._db_path

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._db_path, isolation_level=None, timeout=10.0)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            yield conn
        finally:
            conn.close()

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    # ------------------------------------------------------------------
    # 적재 / 멱등성
    # ------------------------------------------------------------------
    def enqueue(
        self,
        *,
        idempotency_key: str,
        user_id: str,
        command: str,
    ) -> tuple[Job, bool]:
        """job 을 적재한다.

        반환: (job, created). `created=False` 면 같은 `idempotency_key` 로 이미
        적재된 기존 job 을 반환한 것 (AC-11 멱등성).
        """
        if not idempotency_key:
            raise ValueError("idempotency_key 가 비어 있습니다.")
        if not user_id:
            raise ValueError("user_id 가 비어 있습니다.")
        if not command:
            raise ValueError("command 가 비어 있습니다.")

        now = _now_kst_iso()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT * FROM jobs WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if existing is not None:
                conn.execute("COMMIT")
                return _row_to_job(existing), False

            cursor = conn.execute(
                """
                INSERT INTO jobs (idempotency_key, user_id, command, status, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (idempotency_key, user_id, command, STATUS_PENDING, now),
            )
            job_id = cursor.lastrowid
            conn.execute("COMMIT")

        return self.get(job_id), True  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # 조회
    # ------------------------------------------------------------------
    def get(self, job_id: int) -> Job | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
        return _row_to_job(row) if row is not None else None

    def get_by_idempotency_key(self, key: str) -> Job | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM jobs WHERE idempotency_key = ?", (key,)
            ).fetchone()
        return _row_to_job(row) if row is not None else None

    def count_by_status(self, status: str) -> int:
        if status not in _VALID_STATUSES:
            raise ValueError(f"unknown status: {status}")
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM jobs WHERE status = ?", (status,)
            ).fetchone()
        return int(row["n"]) if row is not None else 0

    def latest_done(self, limit: int = 1) -> list[Job]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM jobs
                WHERE status = ?
                ORDER BY datetime(finished_at) DESC, id DESC
                LIMIT ?
                """,
                (STATUS_DONE, int(limit)),
            ).fetchall()
        return [_row_to_job(r) for r in rows]

    # ------------------------------------------------------------------
    # 상태 전이
    # ------------------------------------------------------------------
    def mark_running(self, job_id: int) -> Job | None:
        now = _now_kst_iso()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE jobs
                   SET status = ?, started_at = ?
                 WHERE id = ?
                """,
                (STATUS_RUNNING, now, job_id),
            )
        return self.get(job_id)

    def mark_done(self, job_id: int, *, result_summary: str | None = None) -> Job | None:
        now = _now_kst_iso()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE jobs
                   SET status = ?, finished_at = ?, result_summary = ?
                 WHERE id = ?
                """,
                (STATUS_DONE, now, result_summary, job_id),
            )
        return self.get(job_id)

    def mark_failed(self, job_id: int, *, result_summary: str | None = None) -> Job | None:
        now = _now_kst_iso()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE jobs
                   SET status = ?, finished_at = ?, result_summary = ?
                 WHERE id = ?
                """,
                (STATUS_FAILED, now, result_summary, job_id),
            )
        return self.get(job_id)

    def mark_cancelled(self, job_id: int, *, result_summary: str | None = None) -> Job | None:
        now = _now_kst_iso()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE jobs
                   SET status = ?, finished_at = ?, result_summary = ?
                 WHERE id = ?
                """,
                (STATUS_CANCELLED, now, result_summary, job_id),
            )
        return self.get(job_id)

    # ------------------------------------------------------------------
    # 재시작 복구 (PRD §3.4 — running 잔존 row 는 failed 로 마킹)
    # ------------------------------------------------------------------
    def recover_running_as_failed(
        self, *, reason: str = "이전 세션이 끊겨 작업이 중단됐습니다."
    ) -> list[Job]:
        """`running` 상태로 남아 있는 job 을 모두 `failed` 로 마킹하고 반환.

        반환 리스트는 사용자에게 안내 메시지를 보내기 위한 호출 측 책임.
        """
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE status = ?", (STATUS_RUNNING,)
            ).fetchall()
        recovered: list[Job] = []
        for row in rows:
            job = _row_to_job(row)
            updated = self.mark_failed(job.id, result_summary=reason)
            if updated is not None:
                recovered.append(updated)
        return recovered


def _row_to_job(row: sqlite3.Row | None) -> Job:
    assert row is not None
    return Job(
        id=int(row["id"]),
        idempotency_key=row["idempotency_key"],
        user_id=row["user_id"],
        command=row["command"],
        status=row["status"],
        created_at=row["created_at"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        result_summary=row["result_summary"],
    )
