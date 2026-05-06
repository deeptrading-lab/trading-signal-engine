"""
백그라운드 picker 루프 (Dev Manager — agent integration).

PRD `dev-relay-agent-integration.md` §3.1:
- 데몬 시작 시 thread 1개로 picker 를 띄운다.
- `JobQueue.claim_next_pending` 으로 oldest-first 1건씩 꺼내 `AgentRunner.run_callable`
  로 제출한다.
- 폴링 간격 1초 (MVP 트래픽 1인 단독, 응답성 < 5초 충족).
- shutdown 시 즉시 신규 picking 중단, 진행 중 job 1건은 AgentRunner shutdown
  이 graceful 하게 마친다.

본 모듈은 SDK / Slack 자체에 의존하지 않는다. 호출 측이 `JobHandler` 를 주입
한다 — JobHandler 는 dequeue 된 Job 1건을 받아 결과 텍스트(또는 None) 를 반환.
"""

from __future__ import annotations

import logging
import threading
from typing import Callable

from ai.dev_relay.agent_runner import AgentRunner, AgentTask
from ai.dev_relay.queue import Job, JobQueue

_LOGGER = logging.getLogger("ai.dev_relay.worker")

# 폴링 간격 (PRD §3.1).
DEFAULT_POLL_INTERVAL_S: float = 1.0


# JobHandler: 큐에서 꺼낸 Job 1건을 처리. 반환값은 result_summary(있으면).
# 예외를 raise 해도 picker 가 잡아 `mark_failed` 를 수행한다.
JobHandler = Callable[[Job], str | None]


class JobPicker:
    """`JobQueue.pending` 을 폴링해 1건씩 `AgentRunner` 에 제출하는 백그라운드 thread.

    수명:
    - `start()` — picker thread 를 띄운다 (idempotent).
    - `stop(wait=...)` — 폴링 루프에 종료 플래그를 세우고 join.

    동시 실행 1건은 `AgentRunner(max_workers=1)` 가 이미 보장하므로 picker 자체는
    한 번에 한 job 만 dequeue 하고 future.result() 까지 기다린 뒤 다음 폴링으로
    넘어간다 (busy loop 방지 + 직렬 실행 보장).
    """

    def __init__(
        self,
        *,
        queue: JobQueue,
        runner: AgentRunner,
        handler: JobHandler,
        poll_interval_s: float = DEFAULT_POLL_INTERVAL_S,
        logger: logging.Logger | None = None,
    ) -> None:
        if poll_interval_s <= 0:
            raise ValueError("poll_interval_s 는 0보다 커야 합니다.")
        self._queue = queue
        self._runner = runner
        self._handler = handler
        self._poll_interval_s = poll_interval_s
        self._logger = logger or _LOGGER
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    # --- lifecycle --------------------------------------------------------

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        thread = threading.Thread(
            target=self._run,
            name="dev-relay-picker",
            daemon=True,
        )
        self._thread = thread
        thread.start()

    def stop(self, *, wait: bool = True, timeout: float | None = None) -> None:
        """폴링 루프에 종료 플래그를 세운다.

        진행 중 job 의 graceful shutdown 은 `AgentRunner.shutdown` 호출 측 책임.
        본 메서드는 picker thread 가 다음 폴링 wakeup 시 빠져나오게만 한다.
        """
        self._stop_event.set()
        thread = self._thread
        if wait and thread is not None and thread.is_alive():
            thread.join(timeout=timeout)

    # --- main loop --------------------------------------------------------

    def _run(self) -> None:
        self._logger.info(
            "picker started: poll_interval=%.2fs", self._poll_interval_s
        )
        try:
            while not self._stop_event.is_set():
                claimed = self._claim_one()
                if claimed is None:
                    # pending 없음 — 다음 폴링까지 대기.
                    if self._stop_event.wait(self._poll_interval_s):
                        break
                    continue
                self._dispatch(claimed)
        finally:
            self._logger.info("picker stopped")

    def _claim_one(self) -> Job | None:
        try:
            return self._queue.claim_next_pending()
        except Exception as exc:  # noqa: BLE001
            # DB 에러는 picker 종료 사유가 아니다 — 다음 폴링에 재시도.
            self._logger.error(
                "claim_next_pending 실패 (%s) — 폴링 계속.",
                type(exc).__name__,
            )
            return None

    def _dispatch(self, job: Job) -> None:
        """단일 job 을 AgentRunner 에 제출하고 결과에 따라 큐 상태를 갱신.

        예외/실패는 `mark_failed`. 정상 종료는 `mark_done` (result_summary 포함).
        """
        task = AgentTask(job_id=job.id, command=job.command)

        def _call() -> str | None:
            return self._handler(job)

        try:
            future = self._runner.run_callable(task, _call)
        except RuntimeError as exc:
            # AgentRunner 가 이미 종료된 상황. job 을 failed 로 마킹하고 종료.
            self._logger.warning(
                "AgentRunner 거절: job_id=%d (%s)", job.id, exc
            )
            self._queue.mark_failed(
                job.id,
                result_summary="데몬 종료 중 신규 작업 거절됨.",
            )
            return

        try:
            result = future.result()
        except Exception as exc:  # noqa: BLE001
            # handler 가 자체적으로 사용자 안내·audit 를 처리한다는 가정 (PRD §3.5).
            # picker 단은 큐 상태 전이만 책임진다.
            self._logger.info(
                "job 실패: job_id=%d (%s)", job.id, type(exc).__name__
            )
            self._queue.mark_failed(
                job.id,
                result_summary=f"{type(exc).__name__}: {exc}",
            )
            return

        summary = result if isinstance(result, str) else None
        self._queue.mark_done(job.id, result_summary=summary)


__all__ = [
    "DEFAULT_POLL_INTERVAL_S",
    "JobHandler",
    "JobPicker",
]
