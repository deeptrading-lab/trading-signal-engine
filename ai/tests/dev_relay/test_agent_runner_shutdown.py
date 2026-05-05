"""`AgentRunner.shutdown(timeout)` watchdog 단위 테스트 (Issue #28 항목 2).

PRD §3.7 graceful shutdown 30초 timeout 의 코드 보장. ThreadPoolExecutor 자체는
timeout 을 지원하지 않으므로 별도 watchdog timer 가 강제 종료를 책임진다.
"""

from __future__ import annotations

import logging
import time

import pytest

from ai.dev_relay.agent_runner import AgentRunner, AgentTask


_LOGGER_NAME = "ai.dev_relay.agent_runner"


def _task(job_id: int = 1) -> AgentTask:
    return AgentTask(job_id=job_id, command="echo")


class TestShutdownWatchdog:
    def test_fast_task_completes_within_timeout(self, caplog: pytest.LogCaptureFixture) -> None:
        """빠른 task — watchdog 발동 없이 정상 종료."""
        runner = AgentRunner()
        future = runner.run_callable(_task(), lambda: time.sleep(0.05) or "ok")

        caplog.set_level(logging.WARNING, logger=_LOGGER_NAME)
        start = time.monotonic()
        runner.shutdown(wait=True, timeout=1.0)
        elapsed = time.monotonic() - start

        assert future.result(timeout=0.5) == "ok"
        assert elapsed < 0.5, f"shutdown 이 너무 오래 걸림: {elapsed:.3f}s"
        # watchdog WARNING 이 남지 않아야 한다.
        forced = [
            rec for rec in caplog.records
            if rec.name == _LOGGER_NAME and "forcing" in rec.getMessage()
        ]
        assert forced == []

    def test_slow_task_triggers_force_shutdown(self, caplog: pytest.LogCaptureFixture) -> None:
        """느린 task — timeout 직후 watchdog 이 강제 종료를 발동."""
        runner = AgentRunner()
        runner.run_callable(_task(), lambda: time.sleep(2.0))

        caplog.set_level(logging.WARNING, logger=_LOGGER_NAME)
        start = time.monotonic()
        runner.shutdown(wait=True, timeout=0.2)
        elapsed = time.monotonic() - start

        # timeout=0.2 직후에 풀려나야 한다 (~0.3초 이내).
        assert elapsed < 0.5, f"watchdog 이 강제 종료를 못 함: {elapsed:.3f}s"
        forced = [
            rec for rec in caplog.records
            if rec.name == _LOGGER_NAME and "forcing" in rec.getMessage()
        ]
        assert len(forced) == 1, f"WARNING 1건 기대, got: {[r.getMessage() for r in caplog.records]}"
        assert "0.2" in forced[0].getMessage()

    def test_no_timeout_does_not_register_watchdog(self, caplog: pytest.LogCaptureFixture) -> None:
        """`timeout=None` — 기존 동작 유지, watchdog 미등록."""
        runner = AgentRunner()
        runner.run_callable(_task(), lambda: time.sleep(0.05))

        caplog.set_level(logging.WARNING, logger=_LOGGER_NAME)
        runner.shutdown(wait=True)  # timeout=None default

        forced = [
            rec for rec in caplog.records
            if rec.name == _LOGGER_NAME and "forcing" in rec.getMessage()
        ]
        assert forced == []

    def test_wait_false_skips_watchdog(self, caplog: pytest.LogCaptureFixture) -> None:
        """`wait=False` — watchdog 미등록, 즉시 반환."""
        runner = AgentRunner()
        runner.run_callable(_task(), lambda: time.sleep(0.5))

        caplog.set_level(logging.WARNING, logger=_LOGGER_NAME)
        start = time.monotonic()
        runner.shutdown(wait=False, timeout=0.1)
        elapsed = time.monotonic() - start

        # wait=False 면 즉시 반환되어야 한다 — timeout 인자는 무시.
        assert elapsed < 0.1
        forced = [
            rec for rec in caplog.records
            if rec.name == _LOGGER_NAME and "forcing" in rec.getMessage()
        ]
        assert forced == []
