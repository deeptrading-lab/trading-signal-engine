"""
URL placeholder escape — 발사 직전 컴플라이언스 가드 보조 모듈.

PRD: docs/prd/dev-relay-natural-language.md §3.5.1 (B-2 결정사항)

배경
- 저장소 slug 의 한 토큰이 `ai/coordinator/_compliance.py` 의 `FORBIDDEN_KEYWORDS`
  단어 경계 정규식에 매치된다. 자연어 분기 응답이 GitHub PR/이슈 URL 을 그대로
  인용하면 `safe_say` 가 차단해 사용자 가치 손상이 발생한다.

설계
- `with_urls_escaped(text)` 가 `https?://...` URL 을 placeholder
  (`\\x00URL{n}\\x00`) 로 일시 치환한 (escaped, urls) 튜플을 반환한다.
- `restore_urls(escaped, urls)` 가 원복.
- 호출 측은 escape 후 텍스트로 `find_forbidden_keywords` 검사를 돌리고, 통과 시
  원복 후 발사한다. 차단되는 텍스트는 fallback 으로 치환되어 placeholder 가
  사용자에게 leak 되지 않는다.
- placeholder 형식은 `\\x00` (NUL) 사용 — 사용자 텍스트에 들어올 가능성 0.
- URL 정규식은 PRD 가 박은 형태: `https?://[^\\s<>"]+`.

본 모듈은 `_compliance.py` 본 모듈을 변경하지 않는다 (코디네이터 봇 회귀 0건 보장).
"""

from __future__ import annotations

import re

# URL 정규식 — PRD §3.5.1 박힌 형태. http(s) 스킴만 인정.
_URL_PATTERN: re.Pattern[str] = re.compile(r'https?://[^\s<>"]+')

# placeholder prefix/suffix — NUL 바이트(`\x00`)로 감싸 일반 텍스트와 충돌하지 않게.
_PLACEHOLDER_PREFIX = "\x00URL"
_PLACEHOLDER_SUFFIX = "\x00"


def with_urls_escaped(text: str | None) -> tuple[str, list[str]]:
    """텍스트의 URL 부분을 placeholder 로 치환해 (escaped, urls) 튜플로 반환.

    - URL 이 없으면 원본 텍스트와 빈 리스트를 반환.
    - URL 인덱스는 등장 순서대로 0 부터 시작.
    - placeholder 토큰은 단어 경계 정규식에 걸리지 않는 형태 (`\\x00` 가
      `\\b` 와 매치되지 않는다 — `\\b` 는 `\\w` ↔ non-`\\w` 경계를 본다).
    """
    if not text:
        return text or "", []
    urls: list[str] = []

    def _replace(match: re.Match[str]) -> str:
        index = len(urls)
        urls.append(match.group(0))
        return f"{_PLACEHOLDER_PREFIX}{index}{_PLACEHOLDER_SUFFIX}"

    escaped = _URL_PATTERN.sub(_replace, text)
    return escaped, urls


def restore_urls(escaped: str | None, urls: list[str]) -> str:
    """`with_urls_escaped` 의 역. placeholder 를 원본 URL 로 되돌린다.

    - urls 리스트가 비어 있으면 escaped 를 그대로 반환.
    - placeholder 가 누락된 경우 안전하게 escaped 그대로 반환 (호출 측이
      매치 검사 실패 시 placeholder 가 발사되지 않도록 fallback 으로
      치환할 책임).
    """
    if not escaped:
        return escaped or ""
    if not urls:
        return escaped
    result = escaped
    for index, url in enumerate(urls):
        token = f"{_PLACEHOLDER_PREFIX}{index}{_PLACEHOLDER_SUFFIX}"
        result = result.replace(token, url)
    return result


__all__ = ["with_urls_escaped", "restore_urls"]
