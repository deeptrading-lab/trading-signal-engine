"""reviewer 결과 캐시·렌더링 단위 테스트.

PRD `dev-relay-agent-integration.md` §3.2.
"""

from __future__ import annotations

import pytest

from ai.coordinator._compliance import find_forbidden_keywords
from ai.dev_relay.reviewer import (
    MAX_FINDINGS_DISPLAYED,
    ReviewDetailCache,
    ReviewResult,
    truncate_findings,
)
from ai.dev_relay.slack_renderer import (
    build_review_result_blocks,
    parse_action_value_v2,
)


class TestReviewDetailCache:
    def test_put_and_get(self):
        cache = ReviewDetailCache()
        cache.put(7, "발견 사항 본문")
        assert cache.get(7) == "발견 사항 본문"

    def test_cache_miss_returns_none(self):
        cache = ReviewDetailCache()
        assert cache.get(99) is None

    def test_lru_eviction(self):
        cache = ReviewDetailCache(max_entries=2)
        cache.put(1, "a")
        cache.put(2, "b")
        cache.put(3, "c")
        # 1 이 evict 되어 None.
        assert cache.get(1) is None
        assert cache.get(2) == "b"
        assert cache.get(3) == "c"

    def test_invalid_max(self):
        with pytest.raises(ValueError):
            ReviewDetailCache(max_entries=0)


class TestTruncateFindings:
    def test_short_passthrough(self):
        assert truncate_findings(["a", "b"]) == ["a", "b"]

    def test_truncated(self):
        items = [f"item-{i}" for i in range(5)]
        assert truncate_findings(items) == items[:MAX_FINDINGS_DISPLAYED]

    def test_empty(self):
        assert truncate_findings([]) == []


class TestReviewResultBlocksWithV2Payload:
    """PRD 위험 §1: `[머지 검토]` 페이로드에 PR 번호가 포함되어야 한다."""

    def test_button_value_contains_pr_number(self):
        blocks = build_review_result_blocks(
            pr_number=22,
            summary="요약 본문",
            findings=["발견 1"],
            idempotency_key="abcd-1234",
            job_id=7,
        )
        # actions block 에 두 버튼이 있어야 한다.
        actions = [b for b in blocks if b.get("type") == "actions"]
        assert len(actions) == 1
        elements = actions[0]["elements"]
        action_ids = [e["action_id"] for e in elements]
        assert "merge_review" in action_ids
        assert "view_details" in action_ids

        # 모든 버튼 value 가 v2 포맷이고 pr_number 가 22.
        for el in elements:
            payload = parse_action_value_v2(el["value"])
            assert payload is not None
            assert payload.pr_number == 22
            assert payload.idempotency_key == "abcd-1234"
            assert payload.job_id == 7

    def test_no_findings_falls_back_to_message(self):
        blocks = build_review_result_blocks(
            pr_number=5,
            summary="간단 요약",
            findings=None,
            idempotency_key="key",
            job_id=1,
        )
        # 본문에 "특이사항 없음" 이 포함된다.
        joined = " ".join(
            b.get("text", {}).get("text", "") if isinstance(b.get("text"), dict) else ""
            for b in blocks
        )
        assert "특이사항 없음" in joined

    def test_dirty_summary_replaced_with_fallback(self):
        # 도메인 키워드가 들어가면 원본이 발사 텍스트에 남지 않는다.
        import json

        blocks = build_review_result_blocks(
            pr_number=22,
            summary="this contains signal keyword",
            findings=None,
            idempotency_key="key",
            job_id=1,
        )
        joined = json.dumps(blocks, ensure_ascii=False)
        assert find_forbidden_keywords(joined) == []


class TestReviewResultDataclass:
    def test_construction(self):
        result = ReviewResult(
            summary="요약",
            findings=["a", "b", "c", "d"],
            detail="자세한 본문",
        )
        assert result.summary == "요약"
        assert len(result.findings) == 4
        assert result.detail == "자세한 본문"
