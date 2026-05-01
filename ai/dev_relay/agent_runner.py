"""
Claude Agent SDK 호출 래퍼 (Dev Manager).

PRD §3.2 / §3.8 결정사항:
- 호출 패턴: **동기(sync) 호출 + worker thread**. slack-bolt 이벤트 루프와 분리.
- destructive op 는 **dispatcher 와 본 모듈 두 층 모두**에서 차단 (AC-13).
- LLM 호출 비용 가드 통합은 본 PRD 범위 밖 — 컴플라이언스 가드만 적용.

본 모듈은 SDK 실호출을 직접 수행하지 않는다 (테스트 가능성·토큰 부재 환경 대응).
대신:
- `AgentTask` 가 작업 1건의 메타데이터를 담는다.
- `AgentRunner` 가 worker thread 1개를 보유하며 task 를 sync 로 실행한다.
- `AgentRunner.run_callable` 에 호출자가 임의의 callable 을 넘길 수 있어, 실제 SDK
  호출은 호출 측(`main` 또는 통합 테스트)이 결정한다.
- `assert_no_destructive_intent` 가 SDK 호출 직전·결과 텍스트에 destructive 표지가
  없는지 한 번 더 검사한다.
"""

from __future__ import annotations

import logging
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable

from ai.dev_relay.dispatcher import is_destructive

_LOGGER = logging.getLogger("ai.dev_relay.agent_runner")


class DestructiveOperationBlocked(RuntimeError):
    """destructive 표지가 검출되어 SDK 호출이 차단됐다 (AC-13 2차 차단)."""


@dataclass(frozen=True, slots=True)
class AgentTask:
    """SDK 호출 1건의 메타데이터."""

    job_id: int
    command: str
    pr_number: int | None = None


def assert_no_destructive_intent(text: str | None, *, context: str = "") -> None:
    """텍스트에 destructive 표지가 있으면 `DestructiveOperationBlocked` raise.

    SDK 입력 prompt 와 SDK 출력 결과 양쪽에 적용한다. dispatcher 의 1차 차단은
    사용자 입력만 본다 — 본 함수는 SDK 가 destructive 명령을 제안하는 시나리오까지
    커버한다.
    """
    if is_destructive(text):
        suffix = f" [context={context}]" if context else ""
        _LOGGER.error("destructive op blocked%s", suffix)
        raise DestructiveOperationBlocked(
            f"destructive operation detected{suffix}"
        )


class AgentRunner:
    """단일 worker thread 로 SDK callable 을 직렬 실행한다.

    PRD §3.4 결정사항(동시 1건)과 정합. 두 번째 task 가 들어오면 큐에 쌓여 대기한다.
    `shutdown()` 은 graceful — 진행 중인 task 1건은 끝까지 마치고 종료한다.
    """

    def __init__(self, *, max_workers: int = 1) -> None:
        if max_workers != 1:
            # PRD §3.4 결정사항: 동시 1건. 본 PRD 범위에서는 1로 고정.
            raise ValueError("MVP 에서는 동시 실행 1건만 허용합니다.")
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="dev-relay-agent",
        )
        self._lock = threading.Lock()
        self._closed = False

    def run_callable(
        self,
        task: AgentTask,
        fn: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Future:
        """callable 을 worker thread 에 제출한다.

        호출 측이 SDK 호출 자체를 caller-controlled 한다 — 본 클래스는 직렬화·shutdown
        만 책임진다. callable 의 결과 텍스트가 destructive 표지를 포함하면
        `assert_no_destructive_intent` 가 raise 한다.
        """
        with self._lock:
            if self._closed:
                raise RuntimeError("AgentRunner 는 이미 종료됐습니다.")

        def _wrapped() -> Any:
            _LOGGER.info(
                "agent task start: job_id=%d command=%s",
                task.job_id,
                task.command,
            )
            # SDK 입력에 해당하는 command 를 한 번 더 검사 (이중 안전망).
            assert_no_destructive_intent(task.command, context="agent_input")
            result = fn(*args, **kwargs)
            # 결과가 문자열이면 destructive 표지 검사.
            if isinstance(result, str):
                assert_no_destructive_intent(result, context="agent_output")
            _LOGGER.info("agent task done: job_id=%d", task.job_id)
            return result

        return self._executor.submit(_wrapped)

    def shutdown(self, *, wait: bool = True, timeout: float | None = None) -> None:
        """graceful shutdown.

        `wait=True` 면 진행 중·대기 중 task 가 모두 끝날 때까지 블록한다.
        `timeout` 은 ThreadPoolExecutor 가 직접 지원하지 않으므로 본 PRD 범위에서는
        호출자가 별도 watchdog thread 로 강제 종료를 구현한다.
        """
        with self._lock:
            if self._closed:
                return
            self._closed = True
        # cancel_futures 는 Python 3.9+ 지원.
        self._executor.shutdown(wait=wait, cancel_futures=False)
