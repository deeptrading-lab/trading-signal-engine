"""`shutdown_dev_relay` 헬퍼 단위 테스트.

PR #48 reviewer P2-2 후속 — `_nl_shutdown_flag.set()` 호출 측 통합 검증.

검증 항목:
- 호출 시 `_nl_shutdown_flag` 가 set 된다.
- `AgentRunner.shutdown` 이 동일 호출에서 위임된다.
- 다중 호출 시 idempotent (Event.set 은 이미 set 상태면 no-op).
- flag set 의 사용자 측 효과 (새 NL 진입 거절) 는 기존 AC-NLS-9 (a) 가 보장 —
  본 테스트는 wire-up 만 검증한다.
"""

from __future__ import annotations

import logging

from ai.dev_relay import main as main_mod
from ai.dev_relay.agent_runner import AgentRunner
from ai.dev_relay.main import shutdown_dev_relay


def _fresh_runner() -> AgentRunner:
    return AgentRunner(max_workers=1)


class TestShutdownDevRelayWiring:
    def setup_method(self) -> None:
        # 이전 테스트가 set 한 상태로 남겼을 수 있으므로 매 케이스 시작 시 초기화.
        main_mod._nl_shutdown_flag.clear()
        main_mod._write_shutdown_flag.clear()

    def teardown_method(self) -> None:
        main_mod._nl_shutdown_flag.clear()
        main_mod._write_shutdown_flag.clear()

    def test_sets_nl_shutdown_flag(self) -> None:
        """헬퍼 호출 시 NL flag 가 set 된다."""
        runner = _fresh_runner()
        assert not main_mod._nl_shutdown_flag.is_set()

        shutdown_dev_relay(runner, timeout=1.0)

        assert main_mod._nl_shutdown_flag.is_set()

    def test_sets_write_shutdown_flag(self) -> None:
        """PRD `dev-relay-write-tools.md` §3.6 — write flag 도 set."""
        runner = _fresh_runner()
        assert not main_mod._write_shutdown_flag.is_set()

        shutdown_dev_relay(runner, timeout=1.0)

        assert main_mod._write_shutdown_flag.is_set()

    def test_delegates_to_runner_shutdown(self) -> None:
        """`AgentRunner.shutdown` 이 같은 호출에서 위임된다 — runner 가 closed 상태로 전이."""
        runner = _fresh_runner()

        shutdown_dev_relay(runner, timeout=1.0)

        # 두 번째 task 제출이 RuntimeError 로 거절돼야 한다 (closed 상태 검증).
        try:
            runner.run_callable.__self__  # 안전한 attr 접근 — 아래에서 직접 검증.
        except Exception:
            pass

        # closed 후 제출은 RuntimeError.
        from ai.dev_relay.agent_runner import AgentTask
        task = AgentTask(job_id=1, command="echo")
        raised = False
        try:
            runner.run_callable(task, lambda: "x")
        except RuntimeError:
            raised = True
        assert raised, "runner.shutdown 이 위임되지 않음 — closed 상태 미전이"

    def test_idempotent_double_call(self) -> None:
        """헬퍼 다중 호출 시 예외 없이 정상 처리 (Event.set 은 idempotent,
        AgentRunner.shutdown 도 closed 재호출 시 early return)."""
        runner = _fresh_runner()

        shutdown_dev_relay(runner, timeout=1.0)
        # 두 번째 호출이 raise 하면 fail.
        shutdown_dev_relay(runner, timeout=1.0)

        assert main_mod._nl_shutdown_flag.is_set()

    def test_logger_optional(self) -> None:
        """logger=None 호출도 정상 동작."""
        runner = _fresh_runner()

        shutdown_dev_relay(runner, timeout=1.0, logger=None)

        assert main_mod._nl_shutdown_flag.is_set()

    def test_logger_info_message_emitted(self, caplog) -> None:
        """logger 제공 시 INFO 한 줄이 남는다."""
        runner = _fresh_runner()
        logger = logging.getLogger("ai.dev_relay.test_shutdown_helper")

        caplog.set_level(logging.INFO, logger=logger.name)
        shutdown_dev_relay(runner, timeout=1.0, logger=logger)

        msgs = [rec.getMessage() for rec in caplog.records if rec.name == logger.name]
        assert any("shutdown flag set" in m for m in msgs)
