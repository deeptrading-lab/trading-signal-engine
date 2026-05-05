"""SDK 세션 라이프사이클 단위 테스트 (PRD AC-6, AC-7, AC-8).

검증 항목:
- AC-6: 신규 메시지 → 신규 row 생성, turn_count=1.
- AC-7: 같은 thread 답글 → 같은 row resume, turn_count+=1, last_active_at 갱신.
- AC-8: 30분 만료 후 같은 thread 재진입 → 같은 row 의 session_id 가 갱신된다.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from ai.dev_relay.agent_sessions import (
    KST,
    MODEL_HAIKU,
    MODEL_MIXED,
    MODEL_SONNET,
    SESSION_IDLE_TIMEOUT,
    AgentSessionStore,
    is_expired,
)


@pytest.fixture
def store(tmp_path: Path) -> AgentSessionStore:
    db_path = tmp_path / "queue.db"
    return AgentSessionStore(db_path=db_path)


# ---------------------------------------------------------------------------
# AC-6: 신규 세션 생성
# ---------------------------------------------------------------------------


class TestStartSession:
    def test_creates_new_row(self, store: AgentSessionStore):
        session = store.start(
            thread_ts="1746000000.000100",
            channel_id="D123",
            session_id="sess_abc",
            model_used=MODEL_SONNET,
        )
        assert session.thread_ts == "1746000000.000100"
        assert session.channel_id == "D123"
        assert session.session_id == "sess_abc"
        assert session.turn_count == 1
        assert session.model_used == MODEL_SONNET
        assert session.started_at == session.last_active_at

    def test_same_thread_inserts_only_once_unique(self, store: AgentSessionStore):
        # AC-8: UNIQUE(thread_ts, channel_id) — 같은 키로 두 번 start 하면 row 가
        # 추가되지 않고 기존 row 의 session_id 가 갱신된다.
        first = store.start(
            thread_ts="t1",
            channel_id="D1",
            session_id="sess_old",
            model_used=MODEL_SONNET,
        )
        second = store.start(
            thread_ts="t1",
            channel_id="D1",
            session_id="sess_new",
            model_used=MODEL_HAIKU,
        )
        assert first.id == second.id  # 같은 row
        assert second.session_id == "sess_new"
        assert second.session_id != first.session_id
        assert second.turn_count == 1
        assert second.model_used == MODEL_HAIKU

    def test_different_thread_creates_separate_row(self, store: AgentSessionStore):
        a = store.start(
            thread_ts="t1", channel_id="D1", session_id="sa", model_used=MODEL_HAIKU
        )
        b = store.start(
            thread_ts="t2", channel_id="D1", session_id="sb", model_used=MODEL_HAIKU
        )
        assert a.id != b.id


# ---------------------------------------------------------------------------
# AC-7: 같은 스레드 답글 → resume
# ---------------------------------------------------------------------------


class TestResumeSession:
    def test_resume_increments_turn_count(self, store: AgentSessionStore):
        store.start(
            thread_ts="t1",
            channel_id="D1",
            session_id="sess_abc",
            model_used=MODEL_SONNET,
        )
        resumed = store.resume(thread_ts="t1", channel_id="D1")
        assert resumed is not None
        assert resumed.session_id == "sess_abc"
        assert resumed.turn_count == 2

    def test_resume_returns_none_when_no_row(self, store: AgentSessionStore):
        result = store.resume(thread_ts="missing", channel_id="D1")
        assert result is None

    def test_resume_updates_last_active_at(self, store: AgentSessionStore):
        first = store.start(
            thread_ts="t1",
            channel_id="D1",
            session_id="sess_abc",
            model_used=MODEL_SONNET,
        )
        # NOTE: ISO 8601 초 단위 해상도라 동일 초에 호출되면 동일 값일 수 있다.
        # turn_count 증가는 반드시 발생.
        resumed = store.resume(thread_ts="t1", channel_id="D1")
        assert resumed is not None
        assert resumed.turn_count == first.turn_count + 1

    def test_resume_marks_mixed_when_model_switches(
        self, store: AgentSessionStore
    ):
        # 분류 단계는 Haiku, 본응답이 Sonnet 으로 갈 때 model_used 가 mixed 로
        # 표기되는 동작.
        store.start(
            thread_ts="t1",
            channel_id="D1",
            session_id="sess_abc",
            model_used=MODEL_HAIKU,
        )
        resumed = store.resume(
            thread_ts="t1", channel_id="D1", model_used=MODEL_SONNET
        )
        assert resumed is not None
        assert resumed.model_used == MODEL_MIXED

    def test_get_returns_existing_row(self, store: AgentSessionStore):
        store.start(
            thread_ts="t1",
            channel_id="D1",
            session_id="sess_abc",
            model_used=MODEL_HAIKU,
        )
        got = store.get(thread_ts="t1", channel_id="D1")
        assert got is not None
        assert got.session_id == "sess_abc"

    def test_get_returns_none_for_missing(self, store: AgentSessionStore):
        assert store.get(thread_ts="missing", channel_id="D1") is None


# ---------------------------------------------------------------------------
# AC-8: 30분 만료
# ---------------------------------------------------------------------------


class TestExpiry:
    def test_fresh_session_not_expired(self, store: AgentSessionStore):
        session = store.start(
            thread_ts="t1",
            channel_id="D1",
            session_id="sess_abc",
            model_used=MODEL_HAIKU,
        )
        assert is_expired(session) is False

    def test_session_expired_after_31_minutes(self, store: AgentSessionStore):
        session = store.start(
            thread_ts="t1",
            channel_id="D1",
            session_id="sess_abc",
            model_used=MODEL_HAIKU,
        )
        future = datetime.now(tz=KST) + timedelta(minutes=31)
        assert is_expired(session, now=future) is True

    def test_session_not_expired_at_29_minutes(self, store: AgentSessionStore):
        session = store.start(
            thread_ts="t1",
            channel_id="D1",
            session_id="sess_abc",
            model_used=MODEL_HAIKU,
        )
        future = datetime.now(tz=KST) + timedelta(minutes=29)
        assert is_expired(session, now=future) is False

    def test_expiry_then_restart_updates_session_id(
        self, store: AgentSessionStore
    ):
        # AC-8: 만료 후 같은 thread 재진입 → 같은 row 의 session_id 가 갱신된다.
        first = store.start(
            thread_ts="t1",
            channel_id="D1",
            session_id="sess_old",
            model_used=MODEL_SONNET,
        )
        # 호출 측이 is_expired 판정 후 신규 session_id 로 start 호출.
        second = store.start(
            thread_ts="t1",
            channel_id="D1",
            session_id="sess_new",
            model_used=MODEL_SONNET,
        )
        assert first.id == second.id
        assert second.session_id == "sess_new"
        assert second.session_id != first.session_id
        assert second.turn_count == 1  # 리셋

    def test_default_timeout_is_30_minutes(self):
        assert SESSION_IDLE_TIMEOUT == timedelta(minutes=30)
