"""Block Kit `value` v2 포맷 round-trip 테스트.

PRD `dev-relay-agent-integration.md` §3.2 / §3.3 — `[머지 검토]` / `[승인]` /
`[상세 보기]` 모든 신규 버튼이 본 포맷을 사용한다.
"""

from __future__ import annotations

import pytest

from ai.dev_relay.slack_renderer import (
    ActionPayloadV2,
    build_action_value_v2,
    build_merge_confirm_blocks,
    parse_action_value_v2,
)


class TestRoundTrip:
    def test_basic(self):
        v = build_action_value_v2(pr_number=22, idempotency_key="abcd-1234", job_id=7)
        parsed = parse_action_value_v2(v)
        assert parsed == ActionPayloadV2(
            pr_number=22, idempotency_key="abcd-1234", job_id=7
        )

    def test_format_contract(self):
        # PRD §3.2 본문에 명시된 `pr=<N>;key=<idempotency_key>;job=<job_id>` 패턴.
        v = build_action_value_v2(pr_number=42, idempotency_key="K", job_id=1)
        assert v == "pr=42;key=K;job=1"

    def test_empty_key_rejected(self):
        with pytest.raises(ValueError):
            build_action_value_v2(pr_number=22, idempotency_key="", job_id=1)

    @pytest.mark.parametrize("key", ["a;b", "a=b"])
    def test_separator_in_key_rejected(self, key: str):
        with pytest.raises(ValueError):
            build_action_value_v2(pr_number=22, idempotency_key=key, job_id=1)


class TestParseInvalid:
    @pytest.mark.parametrize(
        "value", [None, "", "no-equals", "pr=22;key=abc", "pr=notint;key=abc;job=1"]
    )
    def test_invalid_returns_none(self, value):
        assert parse_action_value_v2(value) is None

    def test_partial_field_returns_none(self):
        assert parse_action_value_v2("pr=22") is None


class TestMergeConfirmUsesV2:
    def test_buttons_carry_pr_number(self):
        blocks = build_merge_confirm_blocks(
            pr_number=22, idempotency_key="abcd-1234", job_id=7
        )
        actions = [b for b in blocks if b.get("type") == "actions"]
        assert len(actions) == 1
        for el in actions[0]["elements"]:
            payload = parse_action_value_v2(el["value"])
            assert payload is not None
            assert payload.pr_number == 22
            assert payload.job_id == 7
