"""`classify_merge_rejection` 단위 테스트.

PR #51 reviewer P2 #1 후속. `merge_failed` audit 가 단일 `UNKNOWN_ERROR`
분류로 묶이던 케이스를 세분화 — `MergeRejection` 메시지 → 정규화 카테고리.

본 테스트는 audit.jsonl 분석 도구가 분리 카운트할 수 있도록 카테고리 라벨이
안정적임을 회귀로 묶는다.
"""

from __future__ import annotations

import pytest

from ai.dev_relay.merger import (
    REJECTION_CATEGORY_IDEMPOTENCY_MISMATCH,
    REJECTION_CATEGORY_INVALID_PAYLOAD,
    REJECTION_CATEGORY_JOB_ID_MISMATCH,
    REJECTION_CATEGORY_OTHER,
    REJECTION_CATEGORY_RESTART_NO_EXPECTED,
    REJECTION_CATEGORY_UNEXPECTED_ACTION,
    REJECTION_CATEGORY_USER_NOT_ALLOWED,
    REJECTION_REASON_RESTART_NO_EXPECTED,
    MergeRejection,
    classify_merge_rejection,
    validate_approval,
)


class TestClassifyByMessage:
    """문자열 직접 매칭 — 분류 로직 단독 회귀."""

    def test_restart_no_expected(self):
        exc = MergeRejection(REJECTION_REASON_RESTART_NO_EXPECTED)
        assert classify_merge_rejection(exc) == REJECTION_CATEGORY_RESTART_NO_EXPECTED

    def test_idempotency_mismatch(self):
        exc = MergeRejection("idempotency_key mismatch")
        assert classify_merge_rejection(exc) == REJECTION_CATEGORY_IDEMPOTENCY_MISMATCH

    def test_job_id_mismatch(self):
        exc = MergeRejection("job_id mismatch")
        assert classify_merge_rejection(exc) == REJECTION_CATEGORY_JOB_ID_MISMATCH

    def test_user_not_allowed(self):
        exc = MergeRejection("user_id not in allowed list")
        assert classify_merge_rejection(exc) == REJECTION_CATEGORY_USER_NOT_ALLOWED

    @pytest.mark.parametrize(
        "msg",
        [
            "invalid pr_number in payload",
            "missing idempotency_key in payload",
            "invalid job_id in payload",
        ],
    )
    def test_invalid_payload(self, msg):
        exc = MergeRejection(msg)
        assert classify_merge_rejection(exc) == REJECTION_CATEGORY_INVALID_PAYLOAD

    def test_unexpected_action(self):
        exc = MergeRejection("unexpected action_id=foo")
        assert classify_merge_rejection(exc) == REJECTION_CATEGORY_UNEXPECTED_ACTION

    def test_other_fallback(self):
        # 미래의 신규 reason 이 카테고리 추가 없이 도입돼도 `other` 로 떨어진다.
        exc = MergeRejection("some new failure mode")
        assert classify_merge_rejection(exc) == REJECTION_CATEGORY_OTHER


class TestClassifyFromValidateApproval:
    """`validate_approval` 이 실제로 raise 한 `MergeRejection` 도 동일 분류."""

    def _base_kwargs(self) -> dict:
        return {
            "pr_number_in_payload": 22,
            "idempotency_key_in_payload": "abcd",
            "job_id_in_payload": 7,
            "user_id": "U0AE7A54NHL",
            "allowed_user_ids": frozenset({"U0AE7A54NHL"}),
            "action_id": "approve_merge",
        }

    def test_restart(self):
        kwargs = self._base_kwargs() | {
            "expected_idempotency_key": None,
            "expected_job_id": None,
        }
        with pytest.raises(MergeRejection) as info:
            validate_approval(**kwargs)
        assert (
            classify_merge_rejection(info.value)
            == REJECTION_CATEGORY_RESTART_NO_EXPECTED
        )

    def test_idempotency(self):
        kwargs = self._base_kwargs() | {
            "expected_idempotency_key": "different",
            "expected_job_id": 7,
        }
        with pytest.raises(MergeRejection) as info:
            validate_approval(**kwargs)
        assert (
            classify_merge_rejection(info.value)
            == REJECTION_CATEGORY_IDEMPOTENCY_MISMATCH
        )

    def test_user_not_allowed(self):
        kwargs = self._base_kwargs() | {
            "expected_idempotency_key": "abcd",
            "expected_job_id": 7,
            "user_id": "UNOT_IN_LIST",
        }
        with pytest.raises(MergeRejection) as info:
            validate_approval(**kwargs)
        assert (
            classify_merge_rejection(info.value)
            == REJECTION_CATEGORY_USER_NOT_ALLOWED
        )

    def test_invalid_payload_pr(self):
        kwargs = self._base_kwargs() | {
            "expected_idempotency_key": "abcd",
            "expected_job_id": 7,
            "pr_number_in_payload": 0,
        }
        with pytest.raises(MergeRejection) as info:
            validate_approval(**kwargs)
        assert (
            classify_merge_rejection(info.value)
            == REJECTION_CATEGORY_INVALID_PAYLOAD
        )
