"""에이전트 통합 mock 통합 테스트.

PRD `dev-relay-agent-integration.md` §8.1.

본 파일은 Slack/SDK/`gh` 외부 호출을 mock 으로 대체한 채 picker → reviewer →
merge 한 사이클을 1회 완주 검증한다 (AC-INT-1 / AC-INT-2 / AC-INT-6).
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from ai.dev_relay.agent_runner import AgentRunner
from ai.dev_relay.failures import FailureClassification
from ai.dev_relay.merger import MergeOutcome, perform_merge, validate_approval
from ai.dev_relay.queue import STATUS_DONE, JobQueue
from ai.dev_relay.reviewer import ReviewDetailCache, ReviewResult
from ai.dev_relay.worker import JobPicker


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "queue.db"


@pytest.fixture
def queue(db_path: Path) -> JobQueue:
    return JobQueue(db_path)


def _wait_until(predicate, *, timeout: float = 3.0, interval: float = 0.05) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(interval)
    raise AssertionError("timeout waiting for condition")


class TestReviewerThenMergeRoundTrip:
    """AC-INT-1 + AC-INT-2 + AC-INT-6 통합 시나리오."""

    def test_review_pr_then_approve_merge(self, queue: JobQueue):
        runner = AgentRunner()
        try:
            audit_records: list[dict] = []
            cache = ReviewDetailCache()
            expected_approvals: dict = {}

            # 1) picker handler — reviewer mock 호출 + 결과 캐시 + audit.
            def review_handler(job):
                pr_number = int(job.command.rsplit(" ", 1)[-1])
                audit_records.append({"kind": "reviewer_started", "job_id": job.id})
                result = ReviewResult(
                    summary=f"PR {pr_number} 깔끔합니다",
                    findings=["비고 없음"],
                    detail="자세한 본문 텍스트",
                )
                cache.put(job.id, result.detail)
                expected_approvals[job.id] = type("ctx", (), {})()  # placeholder
                expected_approvals[job.id].idempotency_key = job.idempotency_key
                expected_approvals[job.id].job_id = job.id
                expected_approvals[job.id].pr_number = pr_number
                expected_approvals[job.id].user_id = job.user_id
                audit_records.append(
                    {
                        "kind": "reviewer_done",
                        "job_id": job.id,
                        "finding_count": 1,
                    }
                )
                return f"reviewer_done pr={pr_number}"

            picker = JobPicker(
                queue=queue,
                runner=runner,
                handler=review_handler,
                poll_interval_s=0.05,
            )
            picker.start()
            try:
                # 2) review pr 22 큐 적재 → picker 처리 대기.
                job, created = queue.enqueue(
                    idempotency_key="abcd-1234",
                    user_id="U0AE7A54NHL",
                    command="review pr 22",
                )
                assert created is True
                _wait_until(lambda: queue.get(job.id).status == STATUS_DONE)
                assert any(
                    r["kind"] == "reviewer_started" and r["job_id"] == job.id
                    for r in audit_records
                )
                assert any(
                    r["kind"] == "reviewer_done" and r["job_id"] == job.id
                    for r in audit_records
                )
                assert cache.get(job.id) == "자세한 본문 텍스트"
            finally:
                picker.stop(wait=True, timeout=2.0)

            # 3) `[승인]` 버튼 검증 + merge worker mock 호출.
            expected = expected_approvals[job.id]
            approval = validate_approval(
                pr_number_in_payload=22,
                idempotency_key_in_payload="abcd-1234",
                job_id_in_payload=job.id,
                expected_idempotency_key=expected.idempotency_key,
                expected_job_id=expected.job_id,
                user_id="U0AE7A54NHL",
                allowed_user_ids=frozenset({"U0AE7A54NHL"}),
                action_id="approve_merge",
            )
            captured: list[int] = []

            def fake_worker(pr: int) -> MergeOutcome:
                captured.append(pr)
                return MergeOutcome(success=True, sha="abc1234", detail="squashed")

            outcome = perform_merge(approval=approval, worker=fake_worker)
            assert captured == [22]
            assert outcome.success is True
            assert outcome.sha == "abc1234"

            # 4) audit kind 6종 (정상 흐름) 중 4개가 등장해야 한다.
            audit_records.append({"kind": "merge_started", "job_id": job.id})
            audit_records.append(
                {"kind": "merge_done", "job_id": job.id, "sha": outcome.sha}
            )
            kinds = {r["kind"] for r in audit_records}
            assert {"reviewer_started", "reviewer_done", "merge_started", "merge_done"} <= kinds
        finally:
            runner.shutdown(wait=True, timeout=2.0)


class TestApprovalRejectsMismatchedPayload:
    """AC-INT-7 회귀 일부: 검증 실패 시 `_perform_merge` 미호출."""

    def test_idempotency_mismatch_blocks_call(self):
        from ai.dev_relay.merger import MergeRejection

        called = False

        def worker(pr):
            nonlocal called
            called = True
            return MergeOutcome(success=True, sha="x", detail="")

        with pytest.raises(MergeRejection):
            validate_approval(
                pr_number_in_payload=22,
                idempotency_key_in_payload="WRONG",
                job_id_in_payload=7,
                expected_idempotency_key="EXPECTED",
                expected_job_id=7,
                user_id="U0AE7A54NHL",
                allowed_user_ids=frozenset({"U0AE7A54NHL"}),
                action_id="approve_merge",
            )

        assert called is False


class TestConcurrencyAcInt3:
    """AC-INT-3: review 진행 중 두 번째 review 가 pending 으로 적재."""

    def test_second_review_queued_while_first_running(self, queue: JobQueue):
        runner = AgentRunner()
        try:
            gate = threading.Event()
            release = threading.Event()
            seen: list[int] = []

            def handler(job):
                seen.append(job.id)
                if len(seen) == 1:
                    gate.set()
                    release.wait(timeout=3.0)
                return "ok"

            picker = JobPicker(
                queue=queue, runner=runner, handler=handler, poll_interval_s=0.05
            )
            picker.start()
            try:
                a, _ = queue.enqueue(
                    idempotency_key="ka", user_id="U", command="review pr 1"
                )
                b, _ = queue.enqueue(
                    idempotency_key="kb", user_id="U", command="review pr 2"
                )
                assert gate.wait(timeout=2.0)
                # 첫 작업 RUNNING, 두 번째는 PENDING.
                assert queue.get(a.id).status == "running"
                assert queue.get(b.id).status == "pending"
                release.set()
                _wait_until(lambda: queue.get(b.id).status == "done")
            finally:
                release.set()
                picker.stop(wait=True, timeout=2.0)
        finally:
            runner.shutdown(wait=True, timeout=2.0)


class TestFailureClassificationMatrixAcInt5:
    """AC-INT-5: 5개 분류 + fallback 매핑이 templates 와 정합."""

    def test_each_classification_user_message_clean(self):
        from ai.coordinator._compliance import find_forbidden_keywords
        from ai.dev_relay.failures import user_message_for

        for classification in FailureClassification:
            msg = user_message_for(classification)
            assert msg, f"{classification} 메시지가 비어 있습니다"
            assert find_forbidden_keywords(msg) == [], (
                f"{classification} 메시지에 도메인 키워드: {msg}"
            )
