"""백그라운드 picker 단위·통합 테스트.

PRD `dev-relay-agent-integration.md` §3.1 / AC-INT-3 / AC-INT-4.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from ai.dev_relay.agent_runner import AgentRunner
from ai.dev_relay.queue import (
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_RUNNING,
    Job,
    JobQueue,
)
from ai.dev_relay.worker import JobPicker


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "queue.db"


@pytest.fixture
def queue(db_path: Path) -> JobQueue:
    return JobQueue(db_path)


@pytest.fixture
def runner() -> AgentRunner:
    r = AgentRunner()
    yield r
    r.shutdown(wait=True, timeout=2.0)


def _wait_until(predicate, *, timeout: float = 3.0, interval: float = 0.05) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(interval)
    raise AssertionError("timeout waiting for condition")


class TestClaimNextPending:
    def test_oldest_first(self, queue: JobQueue):
        a, _ = queue.enqueue(idempotency_key="a", user_id="U", command="review pr 1")
        # 분리된 created_at 시각을 위해 약간 sleep.
        time.sleep(0.02)
        b, _ = queue.enqueue(idempotency_key="b", user_id="U", command="review pr 2")
        first = queue.claim_next_pending()
        assert first is not None
        assert first.id == a.id
        assert first.status == STATUS_RUNNING
        second = queue.claim_next_pending()
        assert second is not None
        assert second.id == b.id

    def test_returns_none_when_empty(self, queue: JobQueue):
        assert queue.claim_next_pending() is None

    def test_running_jobs_are_not_reclaimed(self, queue: JobQueue):
        a, _ = queue.enqueue(idempotency_key="a", user_id="U", command="review pr 1")
        first = queue.claim_next_pending()
        assert first is not None and first.id == a.id
        # 두 번째 호출 — 같은 job 을 다시 잡으면 안 된다.
        assert queue.claim_next_pending() is None


class TestJobPickerLifecycle:
    def test_picker_processes_pending_job(self, queue: JobQueue, runner: AgentRunner):
        processed: list[int] = []

        def handler(job: Job) -> str | None:
            processed.append(job.id)
            return "ok"

        picker = JobPicker(
            queue=queue, runner=runner, handler=handler, poll_interval_s=0.05
        )
        picker.start()
        try:
            job, _ = queue.enqueue(
                idempotency_key="key-1", user_id="U", command="review pr 1"
            )
            _wait_until(lambda: queue.get(job.id).status == STATUS_DONE, timeout=3.0)
            assert processed == [job.id]
        finally:
            picker.stop(wait=True, timeout=2.0)

    def test_handler_exception_marks_failed(
        self, queue: JobQueue, runner: AgentRunner
    ):
        def handler(job: Job) -> str | None:
            raise RuntimeError("boom")

        picker = JobPicker(
            queue=queue, runner=runner, handler=handler, poll_interval_s=0.05
        )
        picker.start()
        try:
            job, _ = queue.enqueue(
                idempotency_key="key-2", user_id="U", command="review pr 2"
            )
            _wait_until(
                lambda: queue.get(job.id).status == STATUS_FAILED, timeout=3.0
            )
        finally:
            picker.stop(wait=True, timeout=2.0)

    def test_concurrency_second_job_waits(
        self, queue: JobQueue, runner: AgentRunner
    ):
        """AC-INT-3: 첫 job 이 처리 중인 동안 두 번째 job 은 pending 으로 대기."""
        gate = threading.Event()
        release = threading.Event()
        first_seen: list[int] = []

        def handler(job: Job) -> str | None:
            first_seen.append(job.id)
            if len(first_seen) == 1:
                # 첫 job 은 release 신호 받을 때까지 hold.
                gate.set()
                release.wait(timeout=3.0)
            return "ok"

        picker = JobPicker(
            queue=queue, runner=runner, handler=handler, poll_interval_s=0.05
        )
        picker.start()
        try:
            job_a, _ = queue.enqueue(
                idempotency_key="ka", user_id="U", command="review pr 1"
            )
            job_b, _ = queue.enqueue(
                idempotency_key="kb", user_id="U", command="review pr 2"
            )
            # 첫 job 이 핸들러에 진입하면 gate 가 set 된다.
            assert gate.wait(timeout=2.0)
            # 첫 job 이 RUNNING, 두 번째는 PENDING 이어야 한다.
            assert queue.get(job_a.id).status == STATUS_RUNNING
            assert queue.get(job_b.id).status == STATUS_PENDING
            # 첫 job 해제 → 두 번째도 처리되어야.
            release.set()
            _wait_until(lambda: queue.get(job_a.id).status == STATUS_DONE)
            _wait_until(lambda: queue.get(job_b.id).status == STATUS_DONE)
        finally:
            release.set()
            picker.stop(wait=True, timeout=2.0)


class TestRecoveryWithMergeCarveOut:
    """PRD §3.1 머지 carve-out — `merge_started` 후 종결 라인 없는 job 은 unknown."""

    def test_merge_in_flight_marked_unknown(self, queue: JobQueue):
        merge_job, _ = queue.enqueue(
            idempotency_key="m1", user_id="U", command="merge pr 22"
        )
        review_job, _ = queue.enqueue(
            idempotency_key="r1", user_id="U", command="review pr 23"
        )
        queue.mark_running(merge_job.id)
        queue.mark_running(review_job.id)

        failed, unknown = queue.recover_running_as_failed(
            merge_in_flight_job_ids=frozenset({merge_job.id})
        )
        assert [j.id for j in failed] == [review_job.id]
        assert [j.id for j in unknown] == [merge_job.id]
        # status 검증.
        assert queue.get(merge_job.id).status == "unknown"
        assert queue.get(review_job.id).status == STATUS_FAILED
