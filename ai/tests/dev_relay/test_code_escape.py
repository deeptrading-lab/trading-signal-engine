"""코드 스팬 placeholder escape 단위 테스트 (destructive guard false positive 회귀).

검증 항목:
1. 코드 영역이 없으면 원본·빈 리스트.
2. 단일 백틱 코드 스팬 escape + 원복.
3. 트리플 백틱 코드 블록 escape + 원복 (multiline 포함).
4. 두 종류 혼합 시 등장 순서대로 인덱스 부여.
5. placeholder 토큰이 단어 경계 정규식에 매치되지 않는다 (NUL 문자).
6. nl_agent.guard_response_text 통합:
   - 백틱에 감싼 destructive 인용은 통과 (`git reset --hard`).
   - 백틱 없이 destructive 명령형 출력은 차단 (git reset --hard).
   - 코드 블록 안의 destructive 인용도 통과.
"""

from __future__ import annotations

from ai.dev_relay._code_escape import (
    restore_code_spans,
    with_code_spans_escaped,
)
from ai.dev_relay.nl_agent import FALLBACK_RESPONSE, guard_response_text


# ---------------------------------------------------------------------------
# _code_escape 헬퍼 단독 검증
# ---------------------------------------------------------------------------


class TestWithCodeSpansEscaped:
    def test_no_code_returns_original(self):
        text = "그냥 평범한 한국어 본문"
        escaped, spans = with_code_spans_escaped(text)
        assert escaped == text
        assert spans == []

    def test_single_inline_span_escaped(self):
        text = "이건 `git status` 입니다."
        escaped, spans = with_code_spans_escaped(text)
        assert "`git status`" not in escaped
        assert spans == ["`git status`"]
        assert "\x00CODE0\x00" in escaped

    def test_multiple_inline_spans_indexed_in_order(self):
        text = "`a` 과 `b` 가 모두 있다."
        escaped, spans = with_code_spans_escaped(text)
        assert spans == ["`a`", "`b`"]
        assert escaped == "\x00CODE0\x00 과 \x00CODE1\x00 가 모두 있다."

    def test_triple_backtick_code_block_escaped(self):
        text = "위에 코드 블록\n```\nrm -rf /\n```\n아래"
        escaped, spans = with_code_spans_escaped(text)
        assert "rm -rf /" not in escaped
        assert spans == ["```\nrm -rf /\n```"]

    def test_mixed_block_and_span_escaped_in_order(self):
        text = "```\nfoo\n``` 그리고 `bar`"
        escaped, spans = with_code_spans_escaped(text)
        # 블록을 먼저 escape — 인덱스 0 이 블록.
        assert spans == ["```\nfoo\n```", "`bar`"]
        assert "foo" not in escaped
        assert "bar" not in escaped

    def test_empty_string(self):
        escaped, spans = with_code_spans_escaped("")
        assert escaped == ""
        assert spans == []

    def test_none_input(self):
        escaped, spans = with_code_spans_escaped(None)
        assert escaped == ""
        assert spans == []

    def test_unmatched_backtick_not_escaped(self):
        # 백틱 한 개만 있는 텍스트는 매치 안 됨 — 본문에 그대로 남음.
        text = "오늘 ` 코드 스팬 미완성"
        escaped, spans = with_code_spans_escaped(text)
        assert escaped == text
        assert spans == []


class TestRestoreCodeSpans:
    def test_round_trip_single_span(self):
        text = "이건 `git status` 입니다."
        escaped, spans = with_code_spans_escaped(text)
        restored = restore_code_spans(escaped, spans)
        assert restored == text

    def test_round_trip_block_and_span(self):
        text = "위 ```\nfoo\n``` 와 `bar`"
        escaped, spans = with_code_spans_escaped(text)
        restored = restore_code_spans(escaped, spans)
        assert restored == text

    def test_empty_spans_returns_escaped_as_is(self):
        assert restore_code_spans("plain text", []) == "plain text"

    def test_none_input(self):
        assert restore_code_spans(None, []) == ""


class TestPlaceholderDoesNotMatchWordBoundary:
    """placeholder 의 NUL 문자가 destructive substring 검사에 영향을 주지 않는지."""

    def test_placeholder_does_not_contain_destructive_substrings(self):
        # placeholder 자체에 destructive 패턴이 들어가지 않아야 한다.
        from ai.dev_relay.dispatcher import is_destructive

        escaped, _ = with_code_spans_escaped("`git reset --hard`")
        assert not is_destructive(escaped), (
            f"placeholder 에 destructive 표지가 새어들어감: {escaped!r}"
        )


# ---------------------------------------------------------------------------
# nl_agent.guard_response_text 통합 — false positive 회귀 보호
# ---------------------------------------------------------------------------


class TestGuardResponseTextWithCodeEscape:
    def test_inline_backtick_destructive_quote_passes(self):
        """`git reset --hard` 같은 백틱 인용은 destructive 차단 false positive 가 안 일어난다."""
        text = "destructive 명령 (예: `git reset --hard`) 은 봇이 거부합니다."
        safe, blocked = guard_response_text(text)
        assert blocked is None
        assert safe == text

    def test_triple_backtick_block_destructive_quote_passes(self):
        text = "예시:\n```\ngit reset --hard\n```\n이런 명령은 봇이 거부."
        safe, blocked = guard_response_text(text)
        assert blocked is None
        assert safe == text

    def test_plain_destructive_imperative_still_blocked(self):
        """백틱 없이 destructive 명령형 출력은 여전히 차단 (layer 3 가드 보존)."""
        text = "지금 git reset --hard HEAD~1 실행할게요."
        safe, blocked = guard_response_text(text)
        assert blocked == "destructive"
        assert safe == FALLBACK_RESPONSE

    def test_mixed_text_with_safe_quote_and_unsafe_imperative_blocked(self):
        """코드 스팬에 destructive 가 있어도 본문의 명령형은 검출되어 차단."""
        text = "`git reset --hard` 는 거부됩니다. 그래서 git reset --hard 진행하겠습니다."
        safe, blocked = guard_response_text(text)
        assert blocked == "destructive"
        assert safe == FALLBACK_RESPONSE

    def test_empty_text(self):
        safe, blocked = guard_response_text("")
        assert blocked is None
        assert safe == ""

    def test_none_text(self):
        safe, blocked = guard_response_text(None)
        assert blocked is None
        assert safe == ""

    def test_handoff_excerpt_with_backticked_destructive_passes(self):
        """실제 HANDOFF/PRD 인용 패턴 — 가장 흔한 false positive 시나리오."""
        text = (
            "A.6 시나리오: 사용자가 `git reset --hard 해줘` 같은 destructive 명령을 "
            "입력하면 dispatcher 와 PreToolUse hook 양쪽에서 차단됩니다."
        )
        safe, blocked = guard_response_text(text)
        assert blocked is None
        assert safe == text
