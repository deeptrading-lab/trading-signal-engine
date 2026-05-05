"""SQLite 작업 큐 단위 테스트 (PRD §3.4 / AC-11 / AC-14)."""

from __future__ import annotations

from pathlib import Path

import pytest

from ai.dev_relay.queue import (
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_RUNNING,
    JobQueue,
)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "queue.db"


@pytest.fixture
def queue(db_path: Path) -> JobQueue:
    return JobQueue(db_path)


class TestEnqueueIdempotency:
    """AC-11: 같은 idempotency_key 재수신 시 새 row 미적재."""

    def test_first_enqueue_creates_row(self, queue: JobQueue):
        job, created = queue.enqueue(
            idempotency_key="abcd-1234",
            user_id="U0AE7A54NHL",
            command="review pr 22",
        )
        assert created is True
        assert job.id > 0
        assert job.status == STATUS_PENDING
        assert job.command == "review pr 22"

    def test_duplicate_key_returns_existing(self, queue: JobQueue):
        first, created1 = queue.enqueue(
            idempotency_key="abcd-1234",
            user_id="U0AE7A54NHL",
            command="review pr 22",
        )
        assert created1 is True
        second, created2 = queue.enqueue(
            idempotency_key="abcd-1234",
            user_id="U0AE7A54NHL",
            command="review pr 22",
        )
        assert created2 is False
        assert second.id == first.id

    def test_duplicate_key_with_different_command_still_returns_existing(
        self, queue: JobQueue
    ):
        # 멱등성 키가 같으면 같은 이벤트로 간주 — 명령이 달라 보여도 무시.
        first, _ = queue.enqueue(
            idempotency_key="abcd-1234",
            user_id="U0AE7A54NHL",
            command="review pr 22",
        )
        second, created = queue.enqueue(
            idempotency_key="abcd-1234",
            user_id="U0AE7A54NHL",
            command="merge pr 22",
        )
        assert created is False
        assert second.id == first.id
        # 원본 명령이 보존된다.
        assert second.command == "review pr 22"

    def test_different_keys_create_separate_rows(self, queue: JobQueue):
        a, _ = queue.enqueue(
            idempotency_key="key-a",
            user_id="U0AE7A54NHL",
            command="review pr 1",
        )
        b, _ = queue.enqueue(
            idempotency_key="key-b",
            user_id="U0AE7A54NHL",
            command="review pr 2",
        )
        assert a.id != b.id


class TestStateTransitions:
    def test_pending_to_running_to_done(self, queue: JobQueue):
        job, _ = queue.enqueue(
            idempotency_key="key-1",
            user_id="U0AE7A54NHL",
            command="review pr 5",
        )
        assert queue.count_by_status(STATUS_PENDING) == 1
        running = queue.mark_running(job.id)
        assert running is not None
        assert running.status == STATUS_RUNNING
        assert running.started_at is not None
        assert queue.count_by_status(STATUS_RUNNING) == 1
        done = queue.mark_done(job.id, result_summary="리뷰 완료")
        assert done is not None
        assert done.status == STATUS_DONE
        assert done.finished_at is not None
        assert done.result_summary == "리뷰 완료"

    def test_mark_failed_records_summary(self, queue: JobQueue):
        job, _ = queue.enqueue(
            idempotency_key="key-2",
            user_id="U0AE7A54NHL",
            command="review pr 6",
        )
        failed = queue.mark_failed(job.id, result_summary="에이전트 호출 실패")
        assert failed is not None
        assert failed.status == STATUS_FAILED
        assert failed.result_summary == "에이전트 호출 실패"


class TestRecoverRunningAsFailed:
    """PRD §3.4 / AC-8: 재시작 시 running 잔존 row 는 failed 로 마킹."""

    def test_recovery_marks_running_jobs_failed(self, queue: JobQueue):
        job_a, _ = queue.enqueue(
            idempotency_key="key-a",
            user_id="U0AE7A54NHL",
            command="review pr 7",
        )
        queue.mark_running(job_a.id)
        job_b, _ = queue.enqueue(
            idempotency_key="key-b",
            user_id="U0AE7A54NHL",
            command="review pr 8",
        )
        # job_b 는 pending 상태로 둔다.
        recovered = queue.recover_running_as_failed()
        assert len(recovered) == 1
        assert recovered[0].id == job_a.id
        assert recovered[0].status == STATUS_FAILED
        # pending job 은 그대로.
        assert queue.count_by_status(STATUS_PENDING) == 1
        assert queue.count_by_status(STATUS_RUNNING) == 0

    def test_restart_simulation_via_new_instance(self, db_path: Path):
        # 데몬 재시작 시뮬레이션 — 같은 DB 파일을 새 JobQueue 인스턴스로 다시 연다.
        first = JobQueue(db_path)
        job, _ = first.enqueue(
            idempotency_key="restart-key",
            user_id="U0AE7A54NHL",
            command="review pr 9",
        )
        first.mark_running(job.id)

        # 재시작.
        second = JobQueue(db_path)
        recovered = second.recover_running_as_failed()
        assert len(recovered) == 1
        assert recovered[0].id == job.id
        # 같은 멱등성 키 재수신 시 새 row 가 만들어지지 않는다.
        again, created = second.enqueue(
            idempotency_key="restart-key",
            user_id="U0AE7A54NHL",
            command="review pr 9",
        )
        assert created is False
        assert again.id == job.id


class TestStatusCounters:
    def test_count_by_status(self, queue: JobQueue):
        a, _ = queue.enqueue(idempotency_key="k1", user_id="U", command="review pr 1")
        b, _ = queue.enqueue(idempotency_key="k2", user_id="U", command="review pr 2")
        c, _ = queue.enqueue(idempotency_key="k3", user_id="U", command="review pr 3")
        queue.mark_running(a.id)
        queue.mark_done(b.id)
        assert queue.count_by_status(STATUS_PENDING) == 1
        assert queue.count_by_status(STATUS_RUNNING) == 1
        assert queue.count_by_status(STATUS_DONE) == 1

    def test_unknown_status_raises(self, queue: JobQueue):
        with pytest.raises(ValueError):
            queue.count_by_status("nonexistent")


class TestLatestDone:
    def test_returns_most_recently_finished(self, queue: JobQueue):
        a, _ = queue.enqueue(idempotency_key="k1", user_id="U", command="review pr 1")
        b, _ = queue.enqueue(idempotency_key="k2", user_id="U", command="review pr 2")
        queue.mark_done(a.id, result_summary="첫 번째 완료")
        queue.mark_done(b.id, result_summary="두 번째 완료")
        recent = queue.latest_done(limit=1)
        assert len(recent) == 1
        assert recent[0].id == b.id


class TestDirectoryAndFilePermissions:
    """PRD §3.8 — 디렉토리 0700 / 파일 0600."""

    def test_db_directory_exists(self, queue: JobQueue):
        assert queue.db_path.parent.exists()

    def test_db_file_created(self, queue: JobQueue):
        # enqueue 한 번 호출해 파일 생성을 보장.
        queue.enqueue(idempotency_key="x", user_id="U", command="review pr 1")
        assert queue.db_path.exists()
