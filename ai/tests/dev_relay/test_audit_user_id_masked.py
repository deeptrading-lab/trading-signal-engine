"""audit.jsonl 의 `user_id_masked` 필드 누락 회귀 방어 단위 테스트.

PR #25 reviewer Concern 후속 (SESSION_NOTES.md follow-up P2 4 세션 이월) — 사용자별
audit 추적이 끊기지 않도록 `_append_audit` 호출 25곳 중 사용자 컨텍스트가 있는
모든 kind 에 `user_id_masked` 필드가 포함됨을 보장한다.

검증 대상 kind (`ai/dev_relay/main.py` 직접 emit):
- destructive_blocked
- command_received
- session_started / session_resumed
- button_action (cancel_merge / approve_merge / merge_review)
- merge_started / merge_done / merge_failed
- reviewer_started / reviewer_done / reviewer_failed
- reviewer_detail_lookup_failed

(`nl_busy_rejected` 는 이미 `test_handle_command_nl_serialize.py` 가 검증.)

정책: 기존 `"user"` 키는 back-compat 으로 유지하고 `"user_id_masked"` 키를 추가.
시스템 audit (사용자 컨텍스트 없음) 은 `user_id_masked` 필드 자체 생략 — Option A.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ai.dev_relay import main as main_mod
from ai.dev_relay.agent_sessions import AgentSessionStore
from ai.dev_relay.main import _RateLimiter, _handle_command, _handle_natural_language
from ai.dev_relay.nl_agent import HaikuResponse, SonnetResponse
from ai.dev_relay.nl_classifier import ClassificationResult, IntentLabel
from ai.dev_relay.queue import JobQueue


# ---------------------------------------------------------------------------
# 픽스처
# ---------------------------------------------------------------------------


@pytest.fixture
def queue_(tmp_path: Path) -> JobQueue:
    return JobQueue(db_path=tmp_path / "queue.db")


@pytest.fixture
def sessions(tmp_path: Path) -> AgentSessionStore:
    return AgentSessionStore(db_path=tmp_path / "queue.db")


@pytest.fixture
def logger():
    import logging

    return logging.getLogger("test_audit_user_id_masked")


@pytest.fixture
def fake_say():
    sent: list[Any] = []

    def _say(payload=None, *, blocks=None, text=None, **kwargs):
        if blocks is not None or text is not None:
            sent.append({"text": text, "blocks": blocks, **kwargs})
        else:
            sent.append(payload)

    _say.sent = sent  # type: ignore[attr-defined]
    return _say


@pytest.fixture
def audit_path(tmp_path: Path, monkeypatch) -> Path:
    path = tmp_path / "audit.jsonl"
    monkeypatch.setattr(main_mod, "_audit_log_path", lambda: path)
    return path


@pytest.fixture(autouse=True)
def _reset_nl_state():
    """NL 락·shutdown flag 를 테스트 전후 깨끗하게 한다."""
    try:
        main_mod._nl_turn_lock.release()
    except RuntimeError:
        pass
    main_mod._nl_shutdown_flag.clear()
    yield
    try:
        main_mod._nl_turn_lock.release()
    except RuntimeError:
        pass
    main_mod._nl_shutdown_flag.clear()


def _read(audit_path: Path) -> list[dict]:
    if not audit_path.exists():
        return []
    return [
        json.loads(line)
        for line in audit_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _by_kind(records: list[dict], kind: str) -> list[dict]:
    return [r for r in records if r.get("kind") == kind]


# ---------------------------------------------------------------------------
# dispatcher 경유 — destructive_blocked / command_received
# ---------------------------------------------------------------------------


class TestDispatcherAuditUserIdMasked:
    def test_destructive_blocked_has_user_id_masked(
        self, queue_, sessions, fake_say, logger, audit_path
    ):
        _handle_command(
            text="git reset --hard HEAD~5",
            user_id="U0AE7A54NHL",
            event={"client_msg_id": "key-d", "ts": "1.1", "channel": "D1"},
            say=fake_say,
            logger=logger,
            queue=queue_,
            rate_limiter=_RateLimiter(),
        )
        recs = _by_kind(_read(audit_path), "destructive_blocked")
        assert len(recs) == 1
        assert recs[0]["user_id_masked"]
        assert recs[0]["user_id_masked"] != "U0AE7A54NHL"

    def test_command_received_has_user_id_masked(
        self, queue_, sessions, fake_say, logger, audit_path
    ):
        _handle_command(
            text="review pr 22",
            user_id="U0AE7A54NHL",
            event={"client_msg_id": "key-r", "ts": "1.1", "channel": "D1"},
            say=fake_say,
            logger=logger,
            queue=queue_,
            rate_limiter=_RateLimiter(),
        )
        recs = _by_kind(_read(audit_path), "command_received")
        assert len(recs) == 1
        assert recs[0]["user_id_masked"]
        assert recs[0]["user_id_masked"] != "U0AE7A54NHL"


# ---------------------------------------------------------------------------
# 자연어 분기 — session_started / session_resumed
# ---------------------------------------------------------------------------


def _make_fake_runtime(label: IntentLabel = IntentLabel.SUMMARY_REQUEST):
    state: dict[str, Any] = {"sonnet_calls": 0}

    def classifier(_sys, _user):
        return ClassificationResult(label=label, prompt_tokens=10, response_tokens=1)

    def haiku(_text):
        return HaikuResponse(text="고맙습니다.")

    def sonnet(_text, sid):
        state["sonnet_calls"] += 1
        state["last_resume_session_id"] = sid
        return SonnetResponse(
            text="*요약*\n- ok",
            tool_calls=[],
            session_id="sess_new",
        )

    return {
        "classifier": classifier,
        "haiku_responder": haiku,
        "sonnet_responder": sonnet,
        "state": state,
    }


class TestNLSessionAuditUserIdMasked:
    def test_session_started_has_user_id_masked(
        self, sessions, fake_say, logger, audit_path
    ):
        _handle_natural_language(
            text="요약해줘",
            user_id="U0AE7A54NHL",
            event={"client_msg_id": "k1", "ts": "1.1", "channel": "D1"},
            say=fake_say,
            logger=logger,
            sessions=sessions,
            nl_runtime=_make_fake_runtime(),
        )
        recs = _by_kind(_read(audit_path), "session_started")
        assert len(recs) == 1
        assert recs[0]["user_id_masked"]
        assert recs[0]["user_id_masked"] != "U0AE7A54NHL"

    def test_session_resumed_has_user_id_masked(
        self, sessions, fake_say, logger, audit_path
    ):
        from ai.dev_relay.agent_sessions import MODEL_SONNET

        # 직전 turn 의 세션 row 를 사전 적재.
        sessions.start(
            thread_ts="1.1",
            channel_id="D1",
            session_id="sess_existing",
            model_used=MODEL_SONNET,
        )
        _handle_natural_language(
            text="PR #25 자세히",
            user_id="U0AE7A54NHL",
            event={
                "client_msg_id": "k2",
                "ts": "1.2",
                "thread_ts": "1.1",
                "channel": "D1",
            },
            say=fake_say,
            logger=logger,
            sessions=sessions,
            nl_runtime=_make_fake_runtime(IntentLabel.REPORT_REQUEST),
        )
        recs = _by_kind(_read(audit_path), "session_resumed")
        assert len(recs) == 1
        assert recs[0]["user_id_masked"]
        assert recs[0]["user_id_masked"] != "U0AE7A54NHL"


# ---------------------------------------------------------------------------
# button_action / merge_* / reviewer_* — _append_audit 직접 검증
#
# 통합 시나리오 재현 비용이 크므로 _append_audit 직접 호출로 schema 회귀만 방어한다.
# 실 흐름은 test_agent_integration.py / test_handle_command_nl.py 가 별도로 검증.
# ---------------------------------------------------------------------------


class TestAuditSchemaRegression:
    """각 kind 가 `user_id_masked` 필드를 포함하는지 schema 회귀 방어."""

    def test_all_target_kinds_carry_user_id_masked_when_emitted_from_main(
        self, audit_path, monkeypatch
    ):
        """`ai/dev_relay/main.py` 내부에서 실제 emit 되는 모든 record 의 정적 스키마.

        Source 를 직접 grep 해 `_append_audit({...})` 블록에 `user_id_masked` 키가
        존재함을 확인한다. 호출 흐름 재현 없이도 schema 누락 회귀를 잡는다.
        """
        import re

        src = Path(main_mod.__file__).read_text(encoding="utf-8")
        # `_append_audit(` 로 시작해 다음 닫는 `)` 까지의 블록을 모두 추출.
        # nested dict 1단계만 처리 (record 가 평면 dict 라는 코드 컨벤션 의존).
        blocks: list[str] = []
        idx = 0
        while True:
            start = src.find("_append_audit(", idx)
            if start == -1:
                break
            depth = 0
            i = start
            while i < len(src):
                ch = src[i]
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth == 0:
                        blocks.append(src[start : i + 1])
                        idx = i + 1
                        break
                i += 1
            else:
                break

        # `record` 변수 경유 (line 531, 1046 의 pass-through) 는 본 검사에서 제외.
        # 검증 대상은 inline dict literal 만.
        inline_blocks = [b for b in blocks if "{" in b]

        # 각 inline block 의 kind 라벨 추출.
        kind_re = re.compile(r'"kind":\s*"([a-z_]+)"')
        target_kinds = {
            "destructive_blocked",
            "command_received",
            "session_started",
            "session_resumed",
            "button_action",
            "merge_started",
            "merge_done",
            "merge_failed",
            "reviewer_started",
            "reviewer_done",
            "reviewer_failed",
            "reviewer_detail_lookup_failed",
            "nl_busy_rejected",
        }
        seen: dict[str, int] = {}
        missing: list[tuple[str, str]] = []
        for block in inline_blocks:
            match = kind_re.search(block)
            if not match:
                continue
            kind = match.group(1)
            seen[kind] = seen.get(kind, 0) + 1
            if kind in target_kinds and "user_id_masked" not in block:
                # 블록 첫 줄만 잘라서 식별용 단서로 노출.
                first_line = block.splitlines()[0]
                missing.append((kind, first_line))

        assert not missing, (
            "다음 audit emit 지점에 `user_id_masked` 누락:\n"
            + "\n".join(f"  - {k}: {hint}" for k, hint in missing)
        )
        # 적어도 대상 kind 가 모두 emit 지점이 존재하는지.
        for kind in target_kinds:
            assert kind in seen, f"`{kind}` audit emit 지점이 main.py 에서 사라졌습니다."
