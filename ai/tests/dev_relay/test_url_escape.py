"""URL placeholder escape 단위 테스트 (PRD AC-23, B-2 회귀).

검증 항목:
1. GitHub PR/이슈 URL 만 있는 텍스트는 가드 wrapper 가 통과시킨다.
2. URL 밖 본문에 도메인 키워드가 있으면 wrapper 가 차단한다.
3. 정상 통과 시 placeholder (`\\x00URL...\\x00`) 가 결과에 leak 되지 않는다.
4. URL 끝이 잘린 형태도 정규식이 URL 로 인식해 placeholder 처리한다.

본 파일은 `_url_escape` 헬퍼 단독 테스트 + `slack_renderer.guard_text_with_urls`
통합 테스트를 함께 한다.
"""

from __future__ import annotations

from ai.coordinator._compliance import find_forbidden_keywords
from ai.dev_relay import slack_renderer
from ai.dev_relay._url_escape import restore_urls, with_urls_escaped


# ---------------------------------------------------------------------------
# _url_escape 헬퍼 단독 검증
# ---------------------------------------------------------------------------


class TestWithUrlsEscaped:
    def test_no_url_returns_original(self):
        text = "그냥 평범한 한국어 본문"
        escaped, urls = with_urls_escaped(text)
        assert escaped == text
        assert urls == []

    def test_empty_input(self):
        escaped, urls = with_urls_escaped("")
        assert escaped == ""
        assert urls == []
        escaped, urls = with_urls_escaped(None)
        assert escaped == ""
        assert urls == []

    def test_single_url_escaped(self):
        url = "https://github.com/example/repo/pull/25"
        text = f"PR 링크: {url}"
        escaped, urls = with_urls_escaped(text)
        assert urls == [url]
        # placeholder 가 들어가 있어야 한다.
        assert "\x00URL0\x00" in escaped
        # 원본 URL 은 escape 본문에서 사라져야 한다.
        assert url not in escaped

    def test_multiple_urls_indexed(self):
        url_a = "https://github.com/a/b/pull/1"
        url_b = "https://docs.python.org/3/library/re.html"
        text = f"a={url_a} 그리고 b={url_b}"
        escaped, urls = with_urls_escaped(text)
        assert urls == [url_a, url_b]
        assert "\x00URL0\x00" in escaped
        assert "\x00URL1\x00" in escaped

    def test_truncated_url_still_matches(self):
        # AC-23 4번째 케이스 — 끝이 잘린 URL 도 정규식이 URL 로 인식한다.
        truncated = "https://github.com/example/repo-slug-name"
        text = f"see {truncated}"
        escaped, urls = with_urls_escaped(text)
        assert urls == [truncated]
        assert truncated not in escaped


class TestRestoreUrls:
    def test_roundtrip_preserves_original(self):
        original = "본문 https://github.com/foo/bar/pull/1 끝"
        escaped, urls = with_urls_escaped(original)
        restored = restore_urls(escaped, urls)
        assert restored == original

    def test_restore_with_empty_urls(self):
        assert restore_urls("hello", []) == "hello"

    def test_restore_empty_text(self):
        assert restore_urls("", []) == ""
        assert restore_urls(None, []) == ""

    def test_restore_multiple_urls_in_order(self):
        original = (
            "first https://example.com/a then "
            "https://github.com/x/y/pull/2 done"
        )
        escaped, urls = with_urls_escaped(original)
        restored = restore_urls(escaped, urls)
        assert restored == original


# ---------------------------------------------------------------------------
# guard_text_with_urls — 컴플라이언스 가드 통합 (AC-23)
# ---------------------------------------------------------------------------


# 본 테스트 모듈 본문 자체는 도메인 키워드를 평문으로 적지 않는다 — fixture 는
# 가드 정의 지점에서 가져온 첫 키워드를 동적으로 합성한다.
_FIRST_FORBIDDEN = next(iter(sorted(find_forbidden_keywords("trading signal trade"))))


class TestGuardTextWithUrls:
    def test_clean_text_passes(self):
        # 도메인 키워드 없는 텍스트는 그대로 반환.
        assert slack_renderer.guard_text_with_urls("안녕하세요") == "안녕하세요"

    def test_empty_text_passes(self):
        assert slack_renderer.guard_text_with_urls("") == ""
        assert slack_renderer.guard_text_with_urls(None) == ""

    def test_github_url_with_repo_slug_passes(self):
        # AC-23 케이스 1: GitHub URL 만 있는 텍스트는 그대로 발사된다.
        # 저장소 slug 가 가드 키워드를 포함해도 URL 안이라 통과.
        body = (
            "PR 정보: https://github.com/example-org/"
            f"some-{_FIRST_FORBIDDEN}-engine/pull/25 참고하세요"
        )
        result = slack_renderer.guard_text_with_urls(body)
        # 원본 그대로 발사 (URL 살아 있음).
        assert result == body

    def test_keyword_outside_url_blocked(self):
        # AC-23 케이스 2: URL 밖 본문에 도메인 키워드가 있으면 차단.
        body = f"이 작업은 {_FIRST_FORBIDDEN} 영역과 무관합니다"
        result = slack_renderer.guard_text_with_urls(body)
        assert result == slack_renderer.FALLBACK_RESPONSE

    def test_placeholder_does_not_leak(self):
        # AC-23 케이스 3: 정상 통과 시 placeholder 가 결과에 남지 않는다.
        body = (
            "여러 링크: https://github.com/a/b/pull/1 와 "
            "https://docs.anthropic.com/foo 둘 다 봐주세요"
        )
        result = slack_renderer.guard_text_with_urls(body)
        assert "\x00URL" not in result
        assert "\x00" not in result
        # 두 URL 모두 원복되어야 한다.
        assert "https://github.com/a/b/pull/1" in result
        assert "https://docs.anthropic.com/foo" in result

    def test_truncated_url_with_keyword_still_passes(self):
        # AC-23 케이스 4: URL 끝이 잘려도 정규식이 URL 로 잡아 placeholder 처리.
        body = (
            f"잘린 링크 https://github.com/example/some-{_FIRST_FORBIDDEN}-slug "
            "까지만 표시됩니다"
        )
        result = slack_renderer.guard_text_with_urls(body)
        # URL 안 키워드는 escape 되므로 가드 통과 → 원복된 본문이 반환.
        assert result == body
        # placeholder 누수 없음.
        assert "\x00URL" not in result

    def test_keyword_both_inside_and_outside_url_blocked(self):
        # URL 밖에 키워드가 있으면 URL 안 키워드 escape 와 무관하게 차단.
        body = (
            f"본문에 {_FIRST_FORBIDDEN} 가 있고 "
            "링크 https://github.com/a/b/pull/1 도 함께"
        )
        result = slack_renderer.guard_text_with_urls(body)
        assert result == slack_renderer.FALLBACK_RESPONSE
