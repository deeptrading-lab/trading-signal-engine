"""NL 자율 트리거 (Phase 3) 단위 테스트.

PRD: docs/prd/dev-relay-write-tools-nl.md AC-WTN-1 ~ AC-WTN-15

검증 항목:
- AC-WTN-1: `WRITE_REQUEST` 라벨 분류 + audit.
- AC-WTN-2: NL → structured 변환 정상 흐름 + confirm 발사.
- AC-WTN-3: Phase 2 흐름 재진입 — 큐 적재 + worker spawn.
- AC-WTN-4: 모호한 의도 — 변환 거절.
- AC-WTN-5: confirm `[취소]` (회귀 — Phase 2 의 cancel_write 그대로).
- AC-WTN-6: destructive 가드 — NL 진입 시에도 차단.
- AC-WTN-9: 멱등성 — 동일 client_msg_id 재수신.
- AC-WTN-10: rate limit.
- AC-WTN-11: audit log 완전성.
- AC-WTN-12/13: 컴플라이언스 정적 검사 (별도 회귀 = test_compliance.py 그대로).
- AC-WTN-15: AC-WT-7 해소 확인 — write 의도 NL 입력이 자동 변환 + confirm.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

from ai.dev_relay.agent_sessions import AgentSessionStore
from ai.dev_relay.dispatcher import CommandKind, parse
from ai.dev_relay.main import _RateLimiter, _handle_command
from ai.dev_relay.nl_agent import HaikuResponse, SonnetResponse
from ai.dev_relay.nl_classifier import ClassificationResult, IntentLabel
from ai.dev_relay.queue import JobQueue
from ai.dev_relay.write_classifier import (
    ConversionFailReason,
    ConversionRejection,
    ConversionSuccess,
    DEFAULT_CONFIDENCE_THRESHOLD,
    convert,
    parse_conversion_response,
)


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def queue(tmp_path: Path) -> JobQueue:
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
    return logging.getLogger("test_write_tools_nl")


@pytest.fixture(autouse=True)
def isolate_audit(tmp_path: Path, monkeypatch):
    from ai.dev_relay import main as main_mod
    audit_path = tmp_path / "audit.jsonl"
    monkeypatch.setattr(main_mod, "_audit_log_path", lambda: audit_path)
    yield audit_path


@pytest.fixture(autouse=True)
def reset_flags_and_pending(monkeypatch):
    """매 테스트마다 write/nl shutdown flag + write pending 초기화."""
    from ai.dev_relay import main as main_mod
    monkeypatch.setattr(main_mod, "_write_shutdown_flag", threading.Event())
    monkeypatch.setattr(main_mod, "_nl_shutdown_flag", threading.Event())
    monkeypatch.setattr(main_mod, "_nl_turn_lock", threading.Lock())
    monkeypatch.setattr(main_mod, "_write_pending", {})
    yield


def _make_runtime(
    *,
    label: IntentLabel = IntentLabel.WRITE_REQUEST,
    converter_response: str = '{"tool": "apply_patch", "pr": 32, "confidence": 0.9}',
    converter_raises: Exception | None = None,
):
    """SDK 호출 없는 fake runtime — classifier/haiku/sonnet/converter."""
    captured: dict[str, Any] = {
        "classifier_calls": 0,
        "converter_calls": 0,
        "last_converter_text": None,
    }

    def classifier(_sys, _user):
        captured["classifier_calls"] += 1
        return ClassificationResult(label=label, prompt_tokens=287, response_tokens=4)

    def haiku(_text):
        return HaikuResponse(text="ok")

    def sonnet(_text, sid):
        return SonnetResponse(text="ok", session_id=None)

    def converter(_sys, user_text):
        captured["converter_calls"] += 1
        captured["last_converter_text"] = user_text
        if converter_raises is not None:
            raise converter_raises
        return converter_response

    return {
        "classifier": classifier,
        "haiku_responder": haiku,
        "sonnet_responder": sonnet,
        "write_converter": converter,
        "captured": captured,
    }


# ---------------------------------------------------------------------------
# write_classifier — 순수 변환 검증
# ---------------------------------------------------------------------------


class TestParseConversionResponse:
    """AC-WTN-2 / AC-WTN-4 — JSON 검증 단위 케이스."""

    def test_valid_apply_patch(self):
        result = parse_conversion_response(
            '{"tool": "apply_patch", "pr": 32, "confidence": 0.9}'
        )
        assert isinstance(result, ConversionSuccess)
        assert result.tool == "apply_patch"
        assert result.pr_number == 32
        assert result.confidence == 0.9
        assert result.structured_command == "apply patch pr=32"

    def test_valid_commit(self):
        result = parse_conversion_response(
            '{"tool": "commit", "pr": 7, "confidence": 0.8}'
        )
        assert isinstance(result, ConversionSuccess)
        assert result.structured_command == "commit pr=7"

    def test_valid_push(self):
        result = parse_conversion_response(
            '{"tool": "push", "pr": 100, "confidence": 0.95}'
        )
        assert isinstance(result, ConversionSuccess)
        assert result.structured_command == "push pr=100"

    def test_code_fence_wrapped(self):
        raw = '```json\n{"tool": "apply_patch", "pr": 5, "confidence": 0.8}\n```'
        result = parse_conversion_response(raw)
        assert isinstance(result, ConversionSuccess)
        assert result.pr_number == 5

    def test_parse_error_empty(self):
        result = parse_conversion_response("")
        assert isinstance(result, ConversionRejection)
        assert result.reason is ConversionFailReason.PARSE_ERROR

    def test_parse_error_malformed_json(self):
        result = parse_conversion_response("not a json {{")
        assert isinstance(result, ConversionRejection)
        assert result.reason is ConversionFailReason.PARSE_ERROR

    def test_parse_error_non_object(self):
        result = parse_conversion_response("[1, 2, 3]")
        assert isinstance(result, ConversionRejection)
        assert result.reason is ConversionFailReason.PARSE_ERROR

    def test_missing_tool(self):
        result = parse_conversion_response('{"pr": 32, "confidence": 0.9}')
        assert isinstance(result, ConversionRejection)
        assert result.reason is ConversionFailReason.MISSING_FIELD

    def test_missing_pr(self):
        result = parse_conversion_response(
            '{"tool": "apply_patch", "confidence": 0.9}'
        )
        assert isinstance(result, ConversionRejection)
        assert result.reason is ConversionFailReason.MISSING_FIELD

    def test_missing_confidence(self):
        result = parse_conversion_response('{"tool": "apply_patch", "pr": 32}')
        assert isinstance(result, ConversionRejection)
        assert result.reason is ConversionFailReason.MISSING_FIELD

    def test_unknown_tool(self):
        # gh pr create 시도 — 화이트리스트 밖.
        result = parse_conversion_response(
            '{"tool": "create_pr", "pr": 32, "confidence": 0.9}'
        )
        assert isinstance(result, ConversionRejection)
        assert result.reason is ConversionFailReason.UNKNOWN_TOOL

    def test_low_confidence(self):
        result = parse_conversion_response(
            '{"tool": "apply_patch", "pr": 32, "confidence": 0.5}'
        )
        assert isinstance(result, ConversionRejection)
        assert result.reason is ConversionFailReason.LOW_CONFIDENCE

    def test_invalid_pr_negative(self):
        result = parse_conversion_response(
            '{"tool": "apply_patch", "pr": -1, "confidence": 0.9}'
        )
        assert isinstance(result, ConversionRejection)
        assert result.reason is ConversionFailReason.INVALID_PR

    def test_invalid_pr_zero(self):
        result = parse_conversion_response(
            '{"tool": "apply_patch", "pr": 0, "confidence": 0.9}'
        )
        assert isinstance(result, ConversionRejection)
        assert result.reason is ConversionFailReason.INVALID_PR

    def test_invalid_pr_string(self):
        result = parse_conversion_response(
            '{"tool": "apply_patch", "pr": "32", "confidence": 0.9}'
        )
        assert isinstance(result, ConversionRejection)
        assert result.reason is ConversionFailReason.INVALID_PR

    def test_threshold_boundary_exact(self):
        # confidence == threshold 는 통과.
        result = parse_conversion_response(
            f'{{"tool": "apply_patch", "pr": 1, "confidence": {DEFAULT_CONFIDENCE_THRESHOLD}}}'
        )
        assert isinstance(result, ConversionSuccess)


class TestConvert:
    """`convert` 진입점 — SDK callable wrapping."""

    def test_empty_input_short_circuits(self):
        called = {"hit": False}

        def converter(_sys, _user):
            called["hit"] = True
            return '{"tool": "apply_patch", "pr": 1, "confidence": 0.9}'

        result = convert("   ", converter=converter)
        assert isinstance(result, ConversionRejection)
        assert result.reason is ConversionFailReason.PARSE_ERROR
        assert called["hit"] is False

    def test_sdk_exception_falls_back_to_parse_error(self):
        def converter(_sys, _user):
            raise RuntimeError("sdk explosion")

        result = convert("PR 32 패치 적용", converter=converter)
        assert isinstance(result, ConversionRejection)
        assert result.reason is ConversionFailReason.PARSE_ERROR


# ---------------------------------------------------------------------------
# nl_classifier — WRITE_REQUEST 라벨 (AC-WTN-1)
# ---------------------------------------------------------------------------


class TestWriteRequestLabel:
    def test_label_value_stable(self):
        assert IntentLabel.WRITE_REQUEST.value == "WRITE_REQUEST"

    def test_routes_to_write_conversion(self):
        from ai.dev_relay.nl_classifier import routes_to_write_conversion

        assert routes_to_write_conversion(IntentLabel.WRITE_REQUEST) is True
        assert routes_to_write_conversion(IntentLabel.SUMMARY_REQUEST) is False
        assert routes_to_write_conversion(IntentLabel.STATUS_LIKE) is False
        assert routes_to_write_conversion(
            IntentLabel.UNKNOWN_OR_DESTRUCTIVE
        ) is False

    def test_system_prompt_mentions_write_request(self):
        from ai.dev_relay.nl_classifier import CLASSIFY_SYSTEM_PROMPT

        assert "WRITE_REQUEST" in CLASSIFY_SYSTEM_PROMPT
        # destructive 의도는 그대로 UNKNOWN_OR_DESTRUCTIVE 로 분류되도록 강조.
        assert "UNKNOWN_OR_DESTRUCTIVE" in CLASSIFY_SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# AC-WTN-1 / AC-WTN-2 / AC-WTN-3 — 정상 흐름 통합
# ---------------------------------------------------------------------------


class TestNLWriteHappyPath:
    """AC-WTN-1/2/3 — 분류 → 변환 → confirm 발사 → audit 완전성."""

    def test_write_request_routes_to_conversion(
        self, queue, sessions, fake_say, logger, isolate_audit
    ):
        runtime = _make_runtime()
        rate_limiter = _RateLimiter()
        with mock.patch(
            "ai.dev_relay.write_runtime.is_sdk_available", return_value=True
        ), mock.patch(
            "ai.dev_relay.main._build_and_send_write_confirm"
        ) as build_send:
            _handle_command(
                text="PR 32 에 patch 적용해줘",
                user_id="U0AE7A54NHL",
                event={
                    "client_msg_id": "key-nl-wt-1",
                    "ts": "1.1",
                    "channel": "D1",
                },
                say=fake_say,
                logger=logger,
                queue=queue,
                rate_limiter=rate_limiter,
                sessions=sessions,
                nl_runtime=runtime,
            )

        # AC-WTN-1: classifier 호출 1번 + converter 호출 1번.
        assert runtime["captured"]["classifier_calls"] == 1
        assert runtime["captured"]["converter_calls"] == 1
        # 변환에 사용자 NL 텍스트가 그대로 전달됐는지.
        assert runtime["captured"]["last_converter_text"] == "PR 32 에 patch 적용해줘"

        # AC-WTN-3: Phase 2 worker spawn 진입.
        assert build_send.called
        kwargs = build_send.call_args.kwargs
        assert kwargs["kind"] is CommandKind.APPLY_PATCH_PR
        assert kwargs["pr_number"] == 32
        # 변환 투명성 — NL 컨텍스트 전달 확인.
        assert kwargs["nl_original"] == "PR 32 에 patch 적용해줘"
        assert kwargs["structured_command"] == "apply patch pr=32"

        # AC-WTN-11: audit 완전성 — 4 종 신규 + Phase 2 의 patch_requested.
        records = [
            json.loads(line)
            for line in isolate_audit.read_text(encoding="utf-8").splitlines()
            if line
        ]
        kinds = [r.get("kind") for r in records]
        assert "nl_write_classified" in kinds
        assert "nl_write_converted" in kinds
        assert "nl_write_handoff" in kinds
        assert "patch_requested" in kinds
        # 모든 record 가 user_id_masked 키 포함 (PR #50 정책 정합).
        for r in records:
            if r.get("kind") in (
                "nl_write_classified",
                "nl_write_converted",
                "nl_write_handoff",
            ):
                assert "user_id_masked" in r

    def test_commit_intent_converts_to_commit_command(
        self, queue, sessions, fake_say, logger
    ):
        runtime = _make_runtime(
            converter_response='{"tool": "commit", "pr": 32, "confidence": 0.85}',
        )
        rate_limiter = _RateLimiter()
        with mock.patch(
            "ai.dev_relay.write_runtime.is_sdk_available", return_value=True
        ), mock.patch(
            "ai.dev_relay.main._build_and_send_write_confirm"
        ) as build_send:
            _handle_command(
                text="PR 32 커밋 만들어줘",
                user_id="U0AE7A54NHL",
                event={
                    "client_msg_id": "key-nl-wt-2",
                    "ts": "1.1",
                    "channel": "D1",
                },
                say=fake_say,
                logger=logger,
                queue=queue,
                rate_limiter=rate_limiter,
                sessions=sessions,
                nl_runtime=runtime,
            )
        kwargs = build_send.call_args.kwargs
        assert kwargs["kind"] is CommandKind.COMMIT_PR
        assert kwargs["structured_command"] == "commit pr=32"


# ---------------------------------------------------------------------------
# AC-WTN-4 — 모호한 의도 거절
# ---------------------------------------------------------------------------


class TestNLWriteAmbiguous:
    @pytest.mark.parametrize(
        "raw_response,expected_reason",
        [
            ("not a json", ConversionFailReason.PARSE_ERROR),
            ('{"tool": "apply_patch"}', ConversionFailReason.MISSING_FIELD),
            (
                '{"tool": "create_pr", "pr": 1, "confidence": 0.9}',
                ConversionFailReason.UNKNOWN_TOOL,
            ),
            (
                '{"tool": "apply_patch", "pr": 32, "confidence": 0.3}',
                ConversionFailReason.LOW_CONFIDENCE,
            ),
        ],
    )
    def test_rejection_emits_ambiguous_notice(
        self,
        queue,
        sessions,
        fake_say,
        logger,
        isolate_audit,
        raw_response,
        expected_reason,
    ):
        runtime = _make_runtime(converter_response=raw_response)
        rate_limiter = _RateLimiter()
        with mock.patch(
            "ai.dev_relay.write_runtime.is_sdk_available", return_value=True
        ), mock.patch(
            "ai.dev_relay.main._build_and_send_write_confirm"
        ) as build_send:
            _handle_command(
                text="PR 좀 고쳐줘",
                user_id="U0AE7A54NHL",
                event={
                    "client_msg_id": f"key-amb-{expected_reason.value}",
                    "ts": "1.1",
                    "channel": "D1",
                },
                say=fake_say,
                logger=logger,
                queue=queue,
                rate_limiter=rate_limiter,
                sessions=sessions,
                nl_runtime=runtime,
            )
        # confirm 발사 0건.
        assert not build_send.called
        # 모호 안내 발사 1회.
        texts = [s for s in fake_say.sent if isinstance(s, str)]
        assert any(
            "명확하게" in t for t in texts
        ), f"ambiguous notice 미발사: {texts}"
        # audit: nl_write_conversion_failed 라인 + reason.
        records = [
            json.loads(line)
            for line in isolate_audit.read_text(encoding="utf-8").splitlines()
            if line
        ]
        failures = [
            r for r in records if r.get("kind") == "nl_write_conversion_failed"
        ]
        assert failures, "nl_write_conversion_failed audit 누락"
        assert failures[0].get("reason") == expected_reason.value


# ---------------------------------------------------------------------------
# AC-WTN-6 — destructive 가드 (NL 진입 시에도 차단)
# ---------------------------------------------------------------------------


class TestNLWriteDestructiveGuard:
    def test_destructive_nl_input_blocked_pre_classify(
        self, queue, sessions, fake_say, logger, isolate_audit
    ):
        """NL 텍스트 자체가 destructive 표지를 포함 → dispatcher 단계에서 차단.

        분류 SDK 호출 자체에 도달하지 않는다 (dispatcher 의 destructive 1차 차단
        + classify 단계에서 `UNKNOWN_OR_DESTRUCTIVE` fallback 의 다층 가드).
        """
        runtime = _make_runtime()
        rate_limiter = _RateLimiter()
        _handle_command(
            text="PR 32 force push 해줘",
            user_id="U0AE7A54NHL",
            event={"client_msg_id": "key-dg-1", "ts": "1.1", "channel": "D1"},
            say=fake_say,
            logger=logger,
            queue=queue,
            rate_limiter=rate_limiter,
            sessions=sessions,
            nl_runtime=runtime,
        )
        # dispatcher destructive 1차 차단 — classifier 미호출.
        assert runtime["captured"]["classifier_calls"] == 0
        assert runtime["captured"]["converter_calls"] == 0

    def test_classify_to_unknown_destructive_does_not_convert(
        self, queue, sessions, fake_say, logger, isolate_audit
    ):
        """Haiku 가 `UNKNOWN_OR_DESTRUCTIVE` 로 분류한 경우 변환 호출 0건."""
        runtime = _make_runtime(label=IntentLabel.UNKNOWN_OR_DESTRUCTIVE)
        rate_limiter = _RateLimiter()
        with mock.patch(
            "ai.dev_relay.main._build_and_send_write_confirm"
        ) as build_send:
            _handle_command(
                text="이거 좀 해줘",
                user_id="U0AE7A54NHL",
                event={
                    "client_msg_id": "key-dg-2",
                    "ts": "1.1",
                    "channel": "D1",
                },
                say=fake_say,
                logger=logger,
                queue=queue,
                rate_limiter=rate_limiter,
                sessions=sessions,
                nl_runtime=runtime,
            )
        # 분류는 1회, 변환은 0회 — UNKNOWN_OR_DESTRUCTIVE 는 Haiku 짧은 응답.
        assert runtime["captured"]["classifier_calls"] == 1
        assert runtime["captured"]["converter_calls"] == 0
        assert not build_send.called


# ---------------------------------------------------------------------------
# AC-WTN-9 — 멱등성
# ---------------------------------------------------------------------------


class TestNLWriteIdempotency:
    def test_duplicate_client_msg_id_one_queue_row(
        self, queue, sessions, fake_say, logger
    ):
        """같은 client_msg_id 두 번 → queue row 1건 (AC-WTN-9 + AC-WT-11 회귀)."""
        rate_limiter = _RateLimiter()
        runtime = _make_runtime()
        with mock.patch(
            "ai.dev_relay.write_runtime.is_sdk_available", return_value=True
        ), mock.patch(
            "ai.dev_relay.main._build_and_send_write_confirm"
        ):
            for _ in range(2):
                # 매 호출마다 NL turn lock 이 release 되었는지 확인을 위해 새 runtime
                # 도 가능하지만 한 lock 으로 직렬화되므로 그대로.
                runtime["captured"]["classifier_calls"] = 0
                runtime["captured"]["converter_calls"] = 0
                _handle_command(
                    text="PR 32 patch 적용",
                    user_id="U0AE7A54NHL",
                    event={
                        "client_msg_id": "dup-nl-key",
                        "ts": "1.1",
                        "channel": "D1",
                    },
                    say=fake_say,
                    logger=logger,
                    queue=queue,
                    rate_limiter=rate_limiter,
                    sessions=sessions,
                    nl_runtime=runtime,
                )
        from ai.dev_relay.queue import (
            STATUS_PENDING,
            STATUS_RUNNING,
            STATUS_DONE,
            STATUS_FAILED,
        )
        total = sum(
            queue.count_by_status(s)
            for s in (STATUS_PENDING, STATUS_RUNNING, STATUS_DONE, STATUS_FAILED)
        )
        assert total == 1


# ---------------------------------------------------------------------------
# AC-WTN-10 — rate limit
# ---------------------------------------------------------------------------


class TestNLWriteRateLimit:
    def test_fourth_message_within_window_rate_limited(
        self, queue, sessions, fake_say, logger
    ):
        rate_limiter = _RateLimiter()
        runtime = _make_runtime()
        with mock.patch(
            "ai.dev_relay.write_runtime.is_sdk_available", return_value=True
        ), mock.patch(
            "ai.dev_relay.main._build_and_send_write_confirm"
        ):
            for i in range(4):
                _handle_command(
                    text="PR 32 patch 적용",
                    user_id="U0AE7A54NHL",
                    event={
                        "client_msg_id": f"key-rl-{i}",
                        "ts": "1.1",
                        "channel": "D1",
                    },
                    say=fake_say,
                    logger=logger,
                    queue=queue,
                    rate_limiter=rate_limiter,
                    sessions=sessions,
                    nl_runtime=runtime,
                )
        texts = [s for s in fake_say.sent if isinstance(s, str)]
        # 4번째 메시지는 rate limit 안내.
        assert any("잠시" in t for t in texts)


# ---------------------------------------------------------------------------
# 변환 결과 confirm prefix — 변환 투명성 (§3.3.1)
# ---------------------------------------------------------------------------


class TestNLConversionPrefix:
    def test_patch_confirm_blocks_show_nl_prefix(self):
        from ai.dev_relay.slack_renderer import build_patch_confirm_blocks

        blocks = build_patch_confirm_blocks(
            pr_number=32,
            idempotency_key="key",
            job_id=1,
            file_count=3,
            added=12,
            removed=4,
            nl_original="PR 32 에 patch 적용해줘",
            structured_command="apply patch pr=32",
        )
        # section body 에 원본 + 변환 결과가 모두 표시.
        body = blocks[0]["text"]["text"]
        assert "PR 32 에 patch 적용해줘" in body
        assert "apply patch pr=32" in body

    def test_patch_confirm_blocks_no_prefix_when_structured(self):
        """structured 진입에서는 prefix 없음 — Phase 2 회귀 0."""
        from ai.dev_relay.slack_renderer import build_patch_confirm_blocks

        blocks = build_patch_confirm_blocks(
            pr_number=32,
            idempotency_key="key",
            job_id=1,
            file_count=3,
            added=12,
            removed=4,
        )
        body = blocks[0]["text"]["text"]
        # NL prefix 토큰 부재.
        assert "원본:" not in body
        assert "변환:" not in body

    def test_commit_confirm_blocks_show_nl_prefix(self):
        from ai.dev_relay.slack_renderer import build_commit_confirm_blocks

        blocks = build_commit_confirm_blocks(
            pr_number=7,
            idempotency_key="key",
            job_id=2,
            message="문서 추가",
            file_count=1,
            nl_original="PR 7 커밋해줘",
            structured_command="commit pr=7",
        )
        body = blocks[0]["text"]["text"]
        assert "PR 7 커밋해줘" in body
        assert "commit pr=7" in body

    def test_push_confirm_blocks_show_nl_prefix(self):
        from ai.dev_relay.slack_renderer import build_push_confirm_blocks

        blocks = build_push_confirm_blocks(
            pr_number=100,
            idempotency_key="key",
            job_id=3,
            branch="feature/x",
            remote="origin",
            commit_count=2,
            nl_original="PR 100 푸시",
            structured_command="push pr=100",
        )
        body = blocks[0]["text"]["text"]
        assert "PR 100 푸시" in body
        assert "push pr=100" in body


# ---------------------------------------------------------------------------
# 변환 결과 → dispatcher 정규식 매치 (재진입 경로 검증)
# ---------------------------------------------------------------------------


class TestConvertedCommandRoundTrip:
    """변환된 structured_command 가 dispatcher 정규식과 정확히 매치되는지."""

    @pytest.mark.parametrize(
        "raw,kind,pr",
        [
            ("apply patch pr=32", CommandKind.APPLY_PATCH_PR, 32),
            ("commit pr=7", CommandKind.COMMIT_PR, 7),
            ("push pr=100", CommandKind.PUSH_PR, 100),
        ],
    )
    def test_synthesized_command_matches_dispatcher(self, raw, kind, pr):
        parsed = parse(raw)
        assert parsed.kind is kind
        assert parsed.pr_number == pr


# ---------------------------------------------------------------------------
# AC-WTN-7 (회귀) — _nl_turn_lock 직렬화 회귀 0
# ---------------------------------------------------------------------------


class TestNLTurnLockRegression:
    def test_busy_second_concurrent_nl_rejected(
        self, queue, sessions, fake_say, logger
    ):
        """첫 번째 NL turn 이 lock 보유 중 두 번째 NL 메시지는 busy 안내."""
        from ai.dev_relay import main as main_mod

        # lock 을 미리 점유.
        main_mod._nl_turn_lock.acquire()
        try:
            runtime = _make_runtime()
            rate_limiter = _RateLimiter()
            _handle_command(
                text="PR 32 patch 적용",
                user_id="U0AE7A54NHL",
                event={
                    "client_msg_id": "key-busy",
                    "ts": "1.1",
                    "channel": "D1",
                },
                say=fake_say,
                logger=logger,
                queue=queue,
                rate_limiter=rate_limiter,
                sessions=sessions,
                nl_runtime=runtime,
            )
            # 두 번째 진입은 busy 거절 — classifier 호출 0.
            assert runtime["captured"]["classifier_calls"] == 0
            texts = [s for s in fake_say.sent if isinstance(s, str)]
            assert any("처리 중" in t or "잠시" in t for t in texts)
        finally:
            main_mod._nl_turn_lock.release()


# ---------------------------------------------------------------------------
# AC-WTN-15 — Phase 2 AC-WT-7 (DEFERRED) 해소 확인
# ---------------------------------------------------------------------------


class TestACWT7Resolution:
    """AC-WT-7 (PR #54 의 DEFERRED) 가 Phase 3 로 해소됐음을 검증.

    회귀: NL 입력 → write 의도 분류 → SDK 변환 → confirm 다이얼로그 발사 →
    사용자 명시 confirm 없이 적용 X.
    """

    def test_nl_write_intent_emits_confirm_not_immediate_apply(
        self, queue, sessions, fake_say, logger
    ):
        runtime = _make_runtime()
        rate_limiter = _RateLimiter()
        applied_calls = {"hit": False}

        def _fake_execute(*_, **__):
            applied_calls["hit"] = True

        with mock.patch(
            "ai.dev_relay.write_runtime.is_sdk_available", return_value=True
        ), mock.patch(
            "ai.dev_relay.main._build_and_send_write_confirm"
        ) as build_send, mock.patch(
            "ai.dev_relay.main._execute_apply_patch", side_effect=_fake_execute
        ):
            _handle_command(
                text="PR 32 에 patch 적용해줘",
                user_id="U0AE7A54NHL",
                event={
                    "client_msg_id": "key-acwt7",
                    "ts": "1.1",
                    "channel": "D1",
                },
                say=fake_say,
                logger=logger,
                queue=queue,
                rate_limiter=rate_limiter,
                sessions=sessions,
                nl_runtime=runtime,
            )
        # 사용자 confirm 미클릭 — apply 호출 0건.
        assert applied_calls["hit"] is False
        # confirm 발사 진입은 발생.
        assert build_send.called
