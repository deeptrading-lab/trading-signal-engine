"""
WebFetch 도메인 화이트리스트 (Dev Manager 자연어 분기).

PRD: docs/prd/dev-relay-natural-language.md §3.4 / AC-14 / B-3

배경
- WebFetch 도구는 외부 URL 의 본문을 LLM 컨텍스트로 끌어들인다. 사고로
  사내 위키 자료가 LLM 에 노출되는 것을 차단하기 위해 화이트리스트 정책으로
  운영한다.
- 시작 도메인은 PRD/도구 문서가 자주 인용되는 호스트만 보수적으로 통과시킨다.
  추가 도메인은 별도 PRD/리뷰를 거쳐 본 모듈에서 명시적으로 추가.

설계
- `is_allowed(url)` — URL 의 host 가 화이트리스트의 entry 와 정확히 일치하거나
  서브도메인 매치하면 True. 그 외는 False.
- 화이트리스트는 frozenset 으로 고정. 사내 도메인 추가는 본 모듈 변경.
- 정규화: scheme 은 http/https 만 인정, 그 외 (`file://`, `ftp://` 등) 는 거부.
"""

from __future__ import annotations

from urllib.parse import urlparse

# 시작 화이트리스트 (PRD §3.4 / B-3).
# - github.com / api.github.com — PR/이슈/저장소 메타데이터 read.
# - docs.anthropic.com — Claude SDK 문서.
# - docs.python.org — Python 표준 라이브러리 문서.
ALLOWED_HOSTS: frozenset[str] = frozenset(
    {
        "github.com",
        "api.github.com",
        "docs.anthropic.com",
        "docs.python.org",
    }
)


def is_allowed(url: str | None) -> bool:
    """URL 이 WebFetch 화이트리스트를 통과하는지.

    - scheme 은 http/https 만 허용.
    - host 가 ALLOWED_HOSTS 의 entry 와 정확 일치하거나 entry 의 서브도메인이면 True.
    - 빈 문자열 / 형식 오류 / 그 외 host 는 False.
    """
    if not url:
        return False
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    scheme = (parsed.scheme or "").lower()
    if scheme not in {"http", "https"}:
        return False
    host = (parsed.hostname or "").lower()
    if not host:
        return False
    if host in ALLOWED_HOSTS:
        return True
    # 서브도메인 매치는 본 PRD 시작 시점에는 보수적으로 비활성.
    # (필요 시 별도 PRD 로 추가 — host == allowed or host.endswith("." + allowed))
    return False


__all__ = ["ALLOWED_HOSTS", "is_allowed"]
