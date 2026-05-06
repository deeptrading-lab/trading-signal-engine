"""`_perform_merge` 검증 + payload 단위 테스트.

PRD `dev-relay-agent-integration.md` §3.3 / AC-INT-2 / AC-INT-7.
"""

from __future__ import annotations

import pytest

from ai.dev_relay.failures import FailureClassification
from ai.dev_relay.merger import (
    MERGE_STRATEGY,
    ApprovalContext,
    MergeOutcome,
    MergeRejection,
    classify_merge_stderr,
    extract_sha,
    perform_merge,
    validate_approval,
)


_ALLOWED = frozenset({"U0AE7A54NHL"})


class TestValidateApproval:
    def _base_kwargs(self) -> dict:
        return {
            "pr_number_in_payload": 22,
            "idempotency_key_in_payload": "abcd-1234",
            "job_id_in_payload": 7,
            "expected_idempotency_key": "abcd-1234",
            "expected_job_id": 7,
            "user_id": "U0AE7A54NHL",
            "allowed_user_ids": _ALLOWED,
            "action_id": "approve_merge",
        }

    def test_happy_path(self):
        ctx = validate_approval(**self._base_kwargs())
        assert ctx.pr_number == 22
        assert ctx.idempotency_key == "abcd-1234"
        assert ctx.job_id == 7
        assert ctx.user_id == "U0AE7A54NHL"

    def test_wrong_action_id_rejected(self):
        kwargs = self._base_kwargs() | {"action_id": "merge_review"}
        with pytest.raises(MergeRejection):
            validate_approval(**kwargs)

    def test_user_not_in_allow_list(self):
        kwargs = self._base_kwargs() | {"user_id": "Uintruder99"}
        with pytest.raises(MergeRejection):
            validate_approval(**kwargs)

    @pytest.mark.parametrize("bad", [None, 0, -1])
    def test_invalid_pr_number(self, bad):
        kwargs = self._base_kwargs() | {"pr_number_in_payload": bad}
        with pytest.raises(MergeRejection):
            validate_approval(**kwargs)

    def test_missing_idempotency_key(self):
        kwargs = self._base_kwargs() | {"idempotency_key_in_payload": ""}
        with pytest.raises(MergeRejection):
            validate_approval(**kwargs)

    def test_idempotency_key_mismatch(self):
        kwargs = self._base_kwargs() | {"expected_idempotency_key": "OTHER"}
        with pytest.raises(MergeRejection):
            validate_approval(**kwargs)

    def test_job_id_mismatch(self):
        kwargs = self._base_kwargs() | {"expected_job_id": 999}
        with pytest.raises(MergeRejection):
            validate_approval(**kwargs)

    def test_no_expected_relaxed(self):
        # expected 가 None 이면 페이로드 자체만 검증. (예: 캐시 유실 후 fallback)
        kwargs = self._base_kwargs() | {
            "expected_idempotency_key": None,
            "expected_job_id": None,
        }
        ctx = validate_approval(**kwargs)
        assert ctx.pr_number == 22


class TestPerformMerge:
    def test_dispatches_to_worker_with_pr_number(self):
        approval = ApprovalContext(
            pr_number=42,
            idempotency_key="abcd-1234",
            job_id=11,
            user_id="U0AE7A54NHL",
        )
        captured: list[int] = []

        def worker(pr: int) -> MergeOutcome:
            captured.append(pr)
            return MergeOutcome(success=True, sha="deadbeef1234567", detail="ok")

        outcome = perform_merge(approval=approval, worker=worker)
        assert captured == [42]
        assert outcome.success is True
        assert outcome.sha == "deadbeef1234567"

    def test_strategy_is_squash(self):
        # PRD §10 — squash 고정.
        assert MERGE_STRATEGY == "squash"


class TestClassifyMergeStderr:
    @pytest.mark.parametrize(
        "stderr",
        [
            "gh: HTTP 401: Bad credentials",
            "permission denied",
            "403 Forbidden",
            "authentication failed",
        ],
    )
    def test_unauthorized(self, stderr: str):
        assert (
            classify_merge_stderr(stderr)
            is FailureClassification.GITHUB_UNAUTHORIZED
        )

    @pytest.mark.parametrize(
        "stderr",
        [
            "422 Unprocessable Entity",
            "Pull request is not mergeable",
            "checks failed",
            "merge conflict",
        ],
    )
    def test_unprocessable(self, stderr: str):
        assert (
            classify_merge_stderr(stderr)
            is FailureClassification.GITHUB_UNPROCESSABLE
        )

    def test_unknown_fallback(self):
        assert (
            classify_merge_stderr("some random network error")
            is FailureClassification.UNKNOWN_ERROR
        )

    def test_empty_is_unknown(self):
        assert classify_merge_stderr("") is FailureClassification.UNKNOWN_ERROR
        assert classify_merge_stderr(None) is FailureClassification.UNKNOWN_ERROR


class TestExtractSha:
    def test_extracts_short_sha(self):
        out = "Merged PR #22 as squash; commit deadbeef1 on main"
        assert extract_sha(out) == "deadbeef1"

    def test_extracts_long_sha(self):
        out = "Squashed and merged: 1234567890abcdef1234567890abcdef12345678"
        assert extract_sha(out) == "1234567890abcdef1234567890abcdef12345678"

    def test_no_sha_returns_none(self):
        assert extract_sha("All good!") is None
        assert extract_sha("") is None
        assert extract_sha(None) is None


class TestDispatcherDoesNotBlockGhMerge:
    """AC-INT-7 회귀: dispatcher 의 destructive 가드는 `gh pr merge` 를 차단하지 않음."""

    def test_dispatcher_allows_gh_pr_merge(self):
        from ai.dev_relay.dispatcher import is_destructive

        # `gh pr merge 22 --squash --delete-branch` 가 destructive 분류에 떨어지지
        # 않아야 한다 (의도적 destructive op 이지만 사용자 명시 승인 흐름).
        assert is_destructive("gh pr merge 22 --squash --delete-branch") is False

    def test_dispatcher_still_blocks_known_destructive(self):
        from ai.dev_relay.dispatcher import is_destructive

        # 회귀: 기존 차단 대상이 여전히 차단되는지.
        assert is_destructive("git reset --hard HEAD~5") is True
        assert is_destructive("git push --force origin main") is True
        assert is_destructive("git branch -d feature") is True
        assert is_destructive("git clean -fd") is True
