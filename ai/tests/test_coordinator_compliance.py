"""컴플라이언스 가드 단위 테스트.

PRD: docs/prd/coordinator-compliance-module.md

본 파일은 도메인 키워드 검사 로직(`_compliance`)과 응답 발사 가드
(`main.safe_say`) 의 동작을 검증한다. 입력 fixture 문자열에는 검사 대상
키워드가 의도적으로 포함되어 있다(PRD AC-10 예외 조항).
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

from ai.coordinator._compliance import (
    FORBIDDEN_KEYWORDS,
    assert_no_forbidden,
    find_forbidden_keywords,
)
from ai.coordinator.main import FALLBACK_RESPONSE, safe_say


class TestForbiddenKeywordsDefinition:
    """AC-1: 모듈 정의."""

    def test_is_frozenset(self):
        assert isinstance(FORBIDDEN_KEYWORDS, frozenset)

    def test_contains_expected_initial_set(self):
        # PRD §3.1 의 초기 키워드 9종.
        expected = {
            "signal",
            "trade",
            "trading",
            "desk",
            "quant",
            "finance",
            "market",
            "ticker",
            "pnl",
        }
        assert FORBIDDEN_KEYWORDS == frozenset(expected)


class TestFindForbiddenKeywords:
    """AC-2/AC-3: 매치/미매치/대소문자/단어 경계/정렬·중복 제거."""

    def test_no_match(self):
        assert find_forbidden_keywords("안녕하세요. 도움이 필요하신가요?") == []

    def test_empty_returns_empty_list(self):
        assert find_forbidden_keywords("") == []

    def test_none_returns_empty_list(self):
        assert find_forbidden_keywords(None) == []

    def test_single_match(self):
        assert find_forbidden_keywords("Signal received") == ["signal"]

    def test_case_insensitive(self):
        # 대문자/혼합 표기도 모두 소문자 형태로 반환.
        assert find_forbidden_keywords("SIGNAL") == ["signal"]
        assert find_forbidden_keywords("SiGnAl") == ["signal"]

    def test_word_boundary_partial_substring_does_not_match(self):
        # AC-2: `signature` 는 `signal` 로 매치되지 않아야 한다.
        assert find_forbidden_keywords("signature analysis") == []

    def test_word_boundary_with_punctuation(self):
        # 콤마/마침표/괄호는 단어 경계로 간주된다.
        assert find_forbidden_keywords("hello, signal.") == ["signal"]

    def test_multiple_match_sorted_and_deduped(self):
        text = "trade, signal, signal, quant"
        assert find_forbidden_keywords(text) == ["quant", "signal", "trade"]

    def test_returns_lowercase(self):
        # 정렬 + 소문자 형태가 보장되어야 한다.
        result = find_forbidden_keywords("DESK and Market")
        assert result == ["desk", "market"]


class TestAssertNoForbidden:
    """AC-2/AC-3: AssertionError + context."""

    def test_passes_on_clean_text(self):
        assert_no_forbidden("안녕하세요.")  # 예외 없음.

    def test_passes_on_empty(self):
        assert_no_forbidden("")
        assert_no_forbidden(None)

    def test_raises_on_match(self):
        with pytest.raises(AssertionError) as excinfo:
            assert_no_forbidden("Signal received")
        assert "signal" in str(excinfo.value)

    def test_error_message_includes_context(self):
        with pytest.raises(AssertionError) as excinfo:
            assert_no_forbidden("trade now", context="render_demo")
        message = str(excinfo.value)
        assert "render_demo" in message
        assert "trade" in message


class TestFallbackResponseSelfCompliance:
    """AC-7: fallback 메시지 자체가 정책 위반이 아님을 보증."""

    def test_fallback_has_no_forbidden(self):
        assert find_forbidden_keywords(FALLBACK_RESPONSE) == []


class TestSafeSay:
    """AC-5/AC-6: runtime 가드.

    `say` 와 `logger` 는 모두 mock 으로 주입한다 — 실제 Slack 통신·로그 출력은
    하지 않는다.
    """

    def _make_logger(self) -> logging.Logger:
        # 실제 logging.Logger 인스턴스를 만들어두고 error 만 mock 으로 교체하면
        # 실제 호출 시그니처(extra=...) 검증이 자연스럽다.
        logger = logging.getLogger("ai.coordinator.test_safe_say")
        logger.error = MagicMock()  # type: ignore[method-assign]
        return logger

    def test_clean_text_passes_through(self):
        say = MagicMock()
        logger = self._make_logger()
        safe_say(say, "안녕하세요. 도움이 필요하신가요?", logger, context="hello")
        say.assert_called_once_with("안녕하세요. 도움이 필요하신가요?")
        logger.error.assert_not_called()  # type: ignore[attr-defined]

    def test_blocked_text_emits_fallback(self):
        say = MagicMock()
        logger = self._make_logger()
        safe_say(say, "test text contains signal here", logger, context="route_command")
        # 원본은 발사되지 않는다.
        say.assert_called_once_with(FALLBACK_RESPONSE)

    def test_blocked_text_logs_error_with_matched_only(self):
        say = MagicMock()
        logger = self._make_logger()
        safe_say(say, "test text contains signal here", logger, context="route_command")
        logger.error.assert_called_once()  # type: ignore[attr-defined]
        args, kwargs = logger.error.call_args  # type: ignore[attr-defined]
        # 메시지 본문에는 원본 텍스트가 들어가지 않는다.
        assert args[0] == "compliance: blocked response"
        extra = kwargs.get("extra") or {}
        assert extra.get("matched") == ["signal"]
        assert extra.get("context") == "route_command"

    def test_empty_text_passes_through(self):
        say = MagicMock()
        logger = self._make_logger()
        safe_say(say, "", logger)
        say.assert_called_once_with("")
        logger.error.assert_not_called()  # type: ignore[attr-defined]

    def test_none_text_passes_through_as_empty(self):
        say = MagicMock()
        logger = self._make_logger()
        safe_say(say, None, logger)
        say.assert_called_once_with("")
        logger.error.assert_not_called()  # type: ignore[attr-defined]
