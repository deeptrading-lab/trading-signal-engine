"""dispatcher + NL 분기 통합 단위 테스트.

PRD AC-1 / AC-15 / AC-19 / AC-20 / AC-21.

검증 항목:
- AC-1: status / review pr <N> / merge pr <N> 정규식 fast-path 가 NL 분기로
  떨어지지 않는다 — classifier callable 이 호출되지 않음.
- AC-15: dispatcher destructive 1차 차단 회귀.
- AC-19: NL 분기 진입 시 audit 신규 kind 가 모두 기록된다 (간접 검증).
- AC-20: 자기 메시지 무시 회귀.
- AC-21: rate limit 회귀.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from ai.dev_relay.agent_sessions import AgentSessionStore
from ai.dev_relay.dispatcher import CommandKind, parse
from ai.dev_relay.main import _RateLimiter, _handle_command
from ai.dev_relay.nl_agent import HaikuResponse, SonnetResponse
from ai.dev_relay.nl_classifier import ClassificationResult, IntentLabel
from ai.dev_relay.queue import JobQueue


@pytest.fixture
def queue(tmp_path: Path, monkeypatch) -> JobQueue:
    db = tmp_path / "queue.db"
    return JobQueue(db_path=db)


@pytest.fixture
def sessions(tmp_path: Path) -> AgentSessionStore:
    db = tmp_path / "queue.db"
    return AgentSessionStore(db_path=db)


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
def logger():
    import logging

    return logging.getLogger("test")


@pytest.fixture
def fake_runtime():
    """NL runtime — classifier/haiku/sonnet 호출 횟수와 인자를 기록."""
    captured: dict[str, Any] = {
        "classifier_calls": 0,
        "haiku_calls": 0,
        "sonnet_calls": 0,
        "classifier_label": IntentLabel.STATUS_LIKE,
        "haiku_text": "감사합니다.",
        "sonnet_text": "*요약*\n- PR #25 완료",
        "sonnet_session_id": "sess_new",
    }

    def classifier(_sys, _user):
        captured["classifier_calls"] += 1
        captured["last_user_text"] = _user
        return ClassificationResult(
            label=captured["classifier_label"],
            prompt_tokens=287,
            response_tokens=4,
        )

    def haiku(_text):
        captured["haiku_calls"] += 1
        return HaikuResponse(text=captured["haiku_text"])

    def sonnet(_text, sid):
        captured["sonnet_calls"] += 1
        captured["sonnet_resume_session_id"] = sid
        return SonnetResponse(
            text=captured["sonnet_text"],
            tool_calls=[("Bash", "git log -n 20", True)],
            session_id=captured["sonnet_session_id"],
        )

    return {
        "classifier": classifier,
        "haiku_responder": haiku,
        "sonnet_responder": sonnet,
        "captured": captured,
    }


# ---------------------------------------------------------------------------
# AC-1: 정규식 fast-path 회귀 — NL 분기 미진입
# ---------------------------------------------------------------------------


class TestFastPathRegression:
    """status / review pr <N> / merge pr <N> 입력은 LLM 호출 없이 처리."""

    def test_status_does_not_invoke_classifier(
        self, queue, sessions, fake_say, logger, fake_runtime
    ):
        rate_limiter = _RateLimiter()
        _handle_command(
            text="status",
            user_id="U0AE7A54NHL",
            event={"client_msg_id": "key-1", "ts": "1.1", "channel": "D1"},
            say=fake_say,
            logger=logger,
            queue=queue,
            rate_limiter=rate_limiter,
            sessions=sessions,
            nl_runtime=fake_runtime,
        )
        # 분류기가 호출되지 않았어야 한다.
        assert fake_runtime["captured"]["classifier_calls"] == 0
        assert fake_runtime["captured"]["haiku_calls"] == 0
        assert fake_runtime["captured"]["sonnet_calls"] == 0

    def test_review_pr_does_not_invoke_classifier(
        self, queue, sessions, fake_say, logger, fake_runtime
    ):
        rate_limiter = _RateLimiter()
        _handle_command(
            text="review pr 22",
            user_id="U0AE7A54NHL",
            event={"client_msg_id": "key-2", "ts": "1.1", "channel": "D1"},
            say=fake_say,
            logger=logger,
            queue=queue,
            rate_limiter=rate_limiter,
            sessions=sessions,
            nl_runtime=fake_runtime,
        )
        assert fake_runtime["captured"]["classifier_calls"] == 0

    def test_merge_pr_does_not_invoke_classifier(
        self, queue, sessions, fake_say, logger, fake_runtime
    ):
        rate_limiter = _RateLimiter()
        _handle_command(
            text="merge pr 22",
            user_id="U0AE7A54NHL",
            event={"client_msg_id": "key-3", "ts": "1.1", "channel": "D1"},
            say=fake_say,
            logger=logger,
            queue=queue,
            rate_limiter=rate_limiter,
            sessions=sessions,
            nl_runtime=fake_runtime,
        )
        assert fake_runtime["captured"]["classifier_calls"] == 0

    def test_dispatcher_kind_for_fast_paths(self):
        # parse 가 정상적으로 매핑하는지 (회귀 안전망).
        assert parse("status").kind is CommandKind.STATUS
        assert parse("review pr 22").kind is CommandKind.REVIEW_PR
        assert parse("merge pr 22").kind is CommandKind.MERGE_PR


# ---------------------------------------------------------------------------
# AC-15: destructive 자연어 입력 — 분류기 미호출
# ---------------------------------------------------------------------------


class TestDestructiveBlocked:
    def test_destructive_input_skips_classifier(
        self, queue, sessions, fake_say, logger, fake_runtime
    ):
        rate_limiter = _RateLimiter()
        _handle_command(
            text="git reset --hard HEAD~5 해줘",
            user_id="U0AE7A54NHL",
            event={"client_msg_id": "key-d", "ts": "1.1", "channel": "D1"},
            say=fake_say,
            logger=logger,
            queue=queue,
            rate_limiter=rate_limiter,
            sessions=sessions,
            nl_runtime=fake_runtime,
        )
        assert fake_runtime["captured"]["classifier_calls"] == 0


# ---------------------------------------------------------------------------
# 자연어 분기 진입
# ---------------------------------------------------------------------------


class TestNLEntry:
    def test_natural_language_enters_loop(
        self, queue, sessions, fake_say, logger, fake_runtime, tmp_path, monkeypatch
    ):
        # audit log 경로를 tmp 로 우회.
        from ai.dev_relay import main as main_mod

        audit_path = tmp_path / "audit.jsonl"
        monkeypatch.setattr(main_mod, "_audit_log_path", lambda: audit_path)

        # SUMMARY → Sonnet 분기.
        fake_runtime["captured"]["classifier_label"] = IntentLabel.SUMMARY_REQUEST

        rate_limiter = _RateLimiter()
        _handle_command(
            text="지금 해야 할 일 요약해줘",
            user_id="U0AE7A54NHL",
            event={"client_msg_id": "key-nl", "ts": "1.1", "channel": "D1"},
            say=fake_say,
            logger=logger,
            queue=queue,
            rate_limiter=rate_limiter,
            sessions=sessions,
            nl_runtime=fake_runtime,
        )
        assert fake_runtime["captured"]["classifier_calls"] == 1
        assert fake_runtime["captured"]["sonnet_calls"] == 1

        # AC-19: audit 신규 kind 가 기록되었는지.
        text = audit_path.read_text(encoding="utf-8")
        assert "llm_invoked" in text
        assert "llm_classified" in text
        assert "session_started" in text  # 신규 세션.
        assert "tool_call" in text

    def test_status_like_routes_haiku_only(
        self, queue, sessions, fake_say, logger, fake_runtime, tmp_path, monkeypatch
    ):
        from ai.dev_relay import main as main_mod

        audit_path = tmp_path / "audit.jsonl"
        monkeypatch.setattr(main_mod, "_audit_log_path", lambda: audit_path)

        fake_runtime["captured"]["classifier_label"] = IntentLabel.STATUS_LIKE

        rate_limiter = _RateLimiter()
        _handle_command(
            text="고마워",
            user_id="U0AE7A54NHL",
            event={"client_msg_id": "key-h", "ts": "1.1", "channel": "D1"},
            say=fake_say,
            logger=logger,
            queue=queue,
            rate_limiter=rate_limiter,
            sessions=sessions,
            nl_runtime=fake_runtime,
        )
        assert fake_runtime["captured"]["haiku_calls"] == 1
        assert fake_runtime["captured"]["sonnet_calls"] == 0

    def test_session_resume_passes_session_id(
        self, queue, sessions, fake_say, logger, fake_runtime, tmp_path, monkeypatch
    ):
        from ai.dev_relay import main as main_mod
        from ai.dev_relay.agent_sessions import MODEL_SONNET

        audit_path = tmp_path / "audit.jsonl"
        monkeypatch.setattr(main_mod, "_audit_log_path", lambda: audit_path)

        # 사전에 세션 row 를 만들어둔다 (직전 turn 결과).
        sessions.start(
            thread_ts="1.1",
            channel_id="D1",
            session_id="sess_existing",
            model_used=MODEL_SONNET,
        )

        fake_runtime["captured"]["classifier_label"] = IntentLabel.REPORT_REQUEST

        rate_limiter = _RateLimiter()
        _handle_command(
            text="PR #25 자세히",
            user_id="U0AE7A54NHL",
            event={
                "client_msg_id": "key-r",
                "ts": "1.2",
                "thread_ts": "1.1",
                "channel": "D1",
            },
            say=fake_say,
            logger=logger,
            queue=queue,
            rate_limiter=rate_limiter,
            sessions=sessions,
            nl_runtime=fake_runtime,
        )
        # Sonnet 호출이 resume_session_id 를 받았는지.
        assert fake_runtime["captured"]["sonnet_resume_session_id"] == "sess_existing"

        text = audit_path.read_text(encoding="utf-8")
        assert "session_resumed" in text


# ---------------------------------------------------------------------------
# AC-21: rate limit 회귀 — NL 분기 진입 전에 차단
# ---------------------------------------------------------------------------


class TestRateLimit:
    def test_rate_limit_blocks_before_nl(
        self, queue, sessions, fake_say, logger, fake_runtime
    ):
        rate_limiter = _RateLimiter()
        # 5초 윈도우 내 4건째.
        for i in range(4):
            _handle_command(
                text="자유 자연어 입력",
                user_id="U0AE7A54NHL",
                event={
                    "client_msg_id": f"k-{i}",
                    "ts": f"{i}.0",
                    "channel": "D1",
                },
                say=fake_say,
                logger=logger,
                queue=queue,
                rate_limiter=rate_limiter,
                sessions=sessions,
                nl_runtime=fake_runtime,
            )
        # 4번째는 rate limit 에 걸려 NL 분기로 들어가지 않는다.
        # 1~3번째는 NL 진입 (classifier 호출 발생).
        assert fake_runtime["captured"]["classifier_calls"] <= 3


# ---------------------------------------------------------------------------
# nl_runtime 미주입 시 — 기존 unknown 안내 fallback
# ---------------------------------------------------------------------------


class TestNoRuntimeFallback:
    def test_unknown_falls_back_when_no_runtime(
        self, queue, sessions, fake_say, logger
    ):
        # SDK 미설치 / 초기화 실패 시 nl_runtime=None — 기존 unknown 안내가 나간다.
        rate_limiter = _RateLimiter()
        _handle_command(
            text="아무 자연어 입력",
            user_id="U0AE7A54NHL",
            event={"client_msg_id": "k-x", "ts": "1.1", "channel": "D1"},
            say=fake_say,
            logger=logger,
            queue=queue,
            rate_limiter=rate_limiter,
            sessions=None,
            nl_runtime=None,
        )
        # unknown command fallback 메시지가 발사되었어야 한다.
        from ai.dev_relay.slack_renderer import TEMPLATE_UNKNOWN_COMMAND

        assert TEMPLATE_UNKNOWN_COMMAND in fake_say.sent
