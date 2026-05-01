"""
코디네이터 외부 노출 텍스트 가드.

PRD: docs/prd/coordinator-compliance-module.md

회사 Slack 워크스페이스(동료 가시성)에서 봇이 발사하는 응답·표시명 등
외부 노출 텍스트에 도메인 키워드가 새어 나가는 회귀를 막기 위한 단일 가드 모듈.

본 모듈은 다음 두 가지를 담당한다.

1. 도메인 키워드 목록의 **단일 정의 지점** (`FORBIDDEN_KEYWORDS`).
2. 텍스트 검사 헬퍼 두 종 — 매치 목록을 반환하는 `find_forbidden_keywords`,
   매치 시 `AssertionError` 를 raise 하는 `assert_no_forbidden`.

설계 메모
- 단어 경계(`\\b`) + 대소문자 무시. 식별자 부분 매치는 회피 — 예를 들어
  `signature` 같은 단어는 매치되지 않도록 `\\b` 기준으로 끊어서 본다.
- 정규식은 모듈 import 시 1회만 컴파일해 호출 비용을 최소화한다.
- `assert_no_forbidden` 은 테스트용 헬퍼이며, runtime 코드는
  `find_forbidden_keywords` 를 직접 사용해 차단·fallback 흐름을 구성한다.
- 본 모듈에서 키워드 문자열은 `FORBIDDEN_KEYWORDS` 정의 자체에만 등장한다 —
  docstring·주석·로그 텍스트에는 일반어("도메인 키워드")로만 표기.
"""

from __future__ import annotations

import re
from typing import Iterable

# 도메인 키워드의 단일 정의 지점. 추가/삭제는 본 모듈에서만.
# (본 모듈을 제외한 다른 외부 노출 텍스트에는 이 단어들이 등장하면 안 된다.)
FORBIDDEN_KEYWORDS: frozenset[str] = frozenset(
    {
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
)


def _build_pattern(keywords: Iterable[str]) -> re.Pattern[str]:
    """단어 경계 + 대소문자 무시 정규식을 1회 컴파일한다.

    - 길이가 긴 키워드를 먼저 alternation 에 두어 부분 매치 우선순위 이슈를 피한다
      (예: `trading` 이 `trade` 보다 먼저). 단어 경계가 있어도 alternation 순서가
      안전한 쪽이 좋다.
    """
    sorted_keywords = sorted(keywords, key=lambda s: (-len(s), s))
    alternation = "|".join(re.escape(k) for k in sorted_keywords)
    return re.compile(rf"\b(?:{alternation})\b", re.IGNORECASE)


_PATTERN: re.Pattern[str] = _build_pattern(FORBIDDEN_KEYWORDS)


def find_forbidden_keywords(text: str | None) -> list[str]:
    """텍스트에서 발견된 도메인 키워드를 정렬·중복 제거된 리스트로 반환한다.

    - 단어 경계(`\\b`) 기준이므로 식별자 부분 매치는 무시된다.
    - 대소문자 무시. 반환 값은 항상 소문자 형태.
    - `text` 가 `None` 또는 빈 문자열이면 빈 리스트.
    """
    if not text:
        return []
    matches = _PATTERN.findall(text)
    if not matches:
        return []
    return sorted({m.lower() for m in matches})


def assert_no_forbidden(text: str | None, *, context: str = "") -> None:
    """텍스트에 도메인 키워드가 포함되어 있으면 `AssertionError` 를 raise.

    매치 시 에러 메시지는 다음 형태:
        compliance: forbidden keyword(s) found <matched> [context=<context>]: <text>

    `context` 는 어느 응답 경로/렌더러에서 발견됐는지 식별하기 위한 자유 문자열이다.
    """
    matched = find_forbidden_keywords(text)
    if not matched:
        return
    suffix = f" [context={context}]" if context else ""
    raise AssertionError(
        f"compliance: forbidden keyword(s) found {matched}{suffix}: {text!r}"
    )


__all__ = [
    "FORBIDDEN_KEYWORDS",
    "find_forbidden_keywords",
    "assert_no_forbidden",
]
