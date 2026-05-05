"""
코드 스팬 placeholder escape — destructive 검사 false positive 방지 보조 모듈.

PRD: docs/prd/dev-relay-natural-language.md §3.5.1 패턴 (B-2 의 자매)

배경
- `agent_runner.is_destructive` 가 LLM 응답 텍스트에 substring 매치하는데, LLM 이
  destructive op 를 **설명** 하는 경우 (예: "`git reset --hard` 같은 destructive
  op 는 거부됩니다") 가 그대로 차단되는 false positive 발생.
- B-2 (URL escape) 와 동일 패턴: 검사 대상에서 "기술적 인용" 영역만 일시 치환 →
  검사 → 통과 시 원복.

설계
- `with_code_spans_escaped(text)` 가 다음 세 종류를 placeholder 로 치환:
  - 트리플 백틱 코드 블록: ``` ... ```
  - 단일 백틱 코드 스팬: `...`
- placeholder 형식은 `\\x00CODE{n}\\x00` (NUL 사용 — 일반 텍스트 충돌 0).
- `restore_code_spans` 가 원복.
- 호출 측은 escape 후 텍스트로 `is_destructive` / `assert_no_destructive_intent`
  를 돌리고, 통과 시 원복 후 발사한다.

LLM 이 destructive 명령을 **명령형** 으로 (백틱 없이) 출력하는 경우는 본 escape 후에도
substring 매치되어 차단된다 — 의도된 layer 3 가드 역할 보존.

본 모듈은 [`ai/coordinator/_compliance.py`](../coordinator/_compliance.py) 와
[`ai/dev_relay/dispatcher.py`](dispatcher.py) 의 destructive 패턴 자체는 건드리지
않는다 (다른 호출 경로 회귀 0건 보장).
"""

from __future__ import annotations

import re

# 트리플 백틱 코드 블록을 먼저 매치 (단일 백틱보다 우선) — `(?s)` 로 multiline 허용.
_CODE_BLOCK_PATTERN: re.Pattern[str] = re.compile(r"```.*?```", re.DOTALL)
# 단일 백틱 코드 스팬 — 줄바꿈 미허용 (Markdown spec).
_CODE_SPAN_PATTERN: re.Pattern[str] = re.compile(r"`[^`\n]+`")

_PLACEHOLDER_PREFIX = "\x00CODE"
_PLACEHOLDER_SUFFIX = "\x00"


def with_code_spans_escaped(text: str | None) -> tuple[str, list[str]]:
    """텍스트의 코드 블록·스팬을 placeholder 로 치환해 (escaped, spans) 튜플로 반환.

    - 트리플 백틱 블록을 먼저 escape, 그 다음 단일 백틱 스팬.
    - 코드 영역이 없으면 원본과 빈 리스트.
    - placeholder 인덱스는 등장 순서대로 0 부터 시작.
    """
    if not text:
        return text or "", []
    spans: list[str] = []

    def _replace(match: re.Match[str]) -> str:
        index = len(spans)
        spans.append(match.group(0))
        return f"{_PLACEHOLDER_PREFIX}{index}{_PLACEHOLDER_SUFFIX}"

    escaped = _CODE_BLOCK_PATTERN.sub(_replace, text)
    escaped = _CODE_SPAN_PATTERN.sub(_replace, escaped)
    return escaped, spans


def restore_code_spans(escaped: str | None, spans: list[str]) -> str:
    """`with_code_spans_escaped` 의 역. placeholder 를 원본으로 되돌린다."""
    if not escaped:
        return escaped or ""
    if not spans:
        return escaped
    result = escaped
    for index, span in enumerate(spans):
        token = f"{_PLACEHOLDER_PREFIX}{index}{_PLACEHOLDER_SUFFIX}"
        result = result.replace(token, span)
    return result


__all__ = ["with_code_spans_escaped", "restore_code_spans"]
