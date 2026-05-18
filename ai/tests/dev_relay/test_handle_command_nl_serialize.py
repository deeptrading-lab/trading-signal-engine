"""자연어 분기 process-wide 직렬화 단위 테스트.

PRD: docs/prd/dev-relay-nl-serialize.md (AC-NLS-1 ~ AC-NLS-9 + §7 위험 1번)

검증 항목:
- AC-NLS-1: 같은 thread_ts 동시 두 NL — 두 번째 거절. SDK 호출 1건.
- AC-NLS-2: 다른 thread_ts 동시 두 NL — 두 번째 거절 (process-wide).
- AC-NLS-3: turn 종료 후 새 NL 정상 처리.
- AC-NLS-4: structured 진행 중 NL — 회귀 (별도 락이라 NL 정상 처리).
- AC-NLS-5: rate_limiter 협업 — rate limit 우선 도달 시 busy 미발사.
- AC-NLS-6: audit `nl_busy_rejected` 1줄 기록 + 필드 정확히 4개.
- AC-NLS-9: shutdown — 진행 중 1건 graceful, 새 진입 거절.
- §7 위험 1번: 예외 발생 시 락 release (try/finally 검증).
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from ai.dev_relay import main as main_mod
from ai.dev_relay.agent_sessions import AgentSessionStore
from ai.dev_relay.main import (
    TEMPLATE_NL_BUSY,
    _handle_command,
    _handle_natural_language,
    _RateLimiter,
)
from ai.dev_relay.nl_agent import HaikuResponse, SonnetResponse
from ai.dev_relay.nl_classifier import ClassificationResult, IntentLabel
from ai.dev_relay.queue import JobQueue


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def queue(tmp_path: Path) -> JobQueue:
    return JobQueue(db_path=tmp_path / "queue.db")


@pytest.fixture
def sessions(tmp_path: Path) -> AgentSessionStore:
    return AgentSessionStore(db_path=tmp_path / "queue.db")


@pytest.fixture
def logger():
    import logging

    return logging.getLogger("test")


class _RecordingSay:
    """thread-safe say mock — 호출 인자를 모두 캡처."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self._lock = threading.Lock()

    def __call__(self, payload=None, *, blocks=None, text=None, **kwargs):
        with self._lock:
            self.calls.append(
                {
                    "payload": payload,
                    "blocks": blocks,
                    "text": text,
                    **kwargs,
                }
            )


@pytest.fixture
def fake_say():
    return _RecordingSay()


@pytest.fixture(autouse=True)
def reset_nl_lock_and_flag():
    """매 테스트 시작 전 모듈 스코프 락·flag 를 초기 상태로 리셋.

    이전 테스트가 예외로 종료돼 락이 보유 상태로 남거나 shutdown flag 가
    set 된 상태로 남아 후속 테스트가 영구 차단되는 회귀를 막는다.
    """
    # 락이 보유 중이면 release.
    try:
        main_mod._nl_turn_lock.release()
    except RuntimeError:
        pass
    main_mod._nl_shutdown_flag.clear()
    yield
    try:
        main_mod._nl_turn_lock.release()
    except RuntimeError:
        pass
    main_mod._nl_shutdown_flag.clear()


@pytest.fixture
def audit_path(tmp_path: Path, monkeypatch) -> Path:
    """audit.jsonl 경로를 tmp 로 우회."""
    path = tmp_path / "audit.jsonl"
    monkeypatch.setattr(main_mod, "_audit_log_path", lambda: path)
    return path


def _read_audit_lines(audit_path: Path) -> list[dict]:
    if not audit_path.exists():
        return []
    return [
        json.loads(line)
        for line in audit_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _make_runtime(*, delay_s: float = 0.0, label: IntentLabel = IntentLabel.SUMMARY_REQUEST):
    """classifier/haiku/sonnet 호출 횟수를 카운트하는 mock runtime.

    `delay_s` 만큼 sonnet 응답을 지연시켜 동시 진입을 재현한다.
    """
    state: dict[str, Any] = {
        "classifier_calls": 0,
        "haiku_calls": 0,
        "sonnet_calls": 0,
    }
    lock = threading.Lock()

    def classifier(_sys, _user):
        with lock:
            state["classifier_calls"] += 1
        return ClassificationResult(
            label=label,
            prompt_tokens=287,
            response_tokens=4,
        )

    def haiku(_text):
        with lock:
            state["haiku_calls"] += 1
        return HaikuResponse(text="고맙습니다.")

    def sonnet(_text, sid):
        with lock:
            state["sonnet_calls"] += 1
        if delay_s > 0:
            time.sleep(delay_s)
        return SonnetResponse(
            text="*요약*\n- PR 처리 결과",
            tool_calls=[("Bash", "git log -n 5", True)],
            session_id="sess_new",
        )

    return {
        "classifier": classifier,
        "haiku_responder": haiku,
        "sonnet_responder": sonnet,
        "state": state,
    }


# ---------------------------------------------------------------------------
# AC-NLS-1: 같은 thread_ts 동시 두 NL — 두 번째 거절
# ---------------------------------------------------------------------------


class TestNLSerializeSameThread:
    def test_concurrent_same_thread_second_rejected(
        self, sessions, fake_say, logger, audit_path
    ):
        runtime = _make_runtime(delay_s=0.3)

        event = {"client_msg_id": "key-1", "ts": "1.1", "channel": "D1"}

        results: list[BaseException | None] = []

        def _invoke():
            try:
                _handle_natural_language(
                    text="요약해줘",
                    user_id="U0AE7A54NHL",
                    event=event,
                    say=fake_say,
                    logger=logger,
                    sessions=sessions,
                    nl_runtime=runtime,
                )
                results.append(None)
            except BaseException as exc:  # noqa: BLE001
                results.append(exc)

        t1 = threading.Thread(target=_invoke)
        t2 = threading.Thread(target=_invoke)
        t1.start()
        # 첫 번째 진입이 락을 잡을 시간 확보.
        time.sleep(0.05)
        t2.start()
        t1.join(timeout=2.0)
        t2.join(timeout=2.0)

        assert all(r is None for r in results)
        # SDK 호출 정확히 1건.
        assert runtime["state"]["sonnet_calls"] == 1
        # busy 안내가 say 호출에 포함되어 있어야 한다.
        payloads = [c["payload"] for c in fake_say.calls]
        assert TEMPLATE_NL_BUSY in payloads
        # audit 에 `nl_busy_rejected` 1줄.
        records = _read_audit_lines(audit_path)
        busy = [r for r in records if r.get("kind") == "nl_busy_rejected"]
        assert len(busy) == 1


# ---------------------------------------------------------------------------
# AC-NLS-2: 다른 thread_ts 동시 두 NL — 두 번째 거절 (process-wide)
# ---------------------------------------------------------------------------


class TestNLSerializeDifferentThread:
    def test_concurrent_different_thread_second_rejected(
        self, sessions, fake_say, logger, audit_path
    ):
        runtime = _make_runtime(delay_s=0.3)

        event_a = {"client_msg_id": "key-a", "ts": "1.1", "channel": "D1"}
        event_b = {"client_msg_id": "key-b", "ts": "2.1", "channel": "D2"}

        def _invoke(ev):
            _handle_natural_language(
                text="요약해줘",
                user_id="U0AE7A54NHL",
                event=ev,
                say=fake_say,
                logger=logger,
                sessions=sessions,
                nl_runtime=runtime,
            )

        t1 = threading.Thread(target=_invoke, args=(event_a,))
        t2 = threading.Thread(target=_invoke, args=(event_b,))
        t1.start()
        time.sleep(0.05)
        t2.start()
        t1.join(timeout=2.0)
        t2.join(timeout=2.0)

        assert runtime["state"]["sonnet_calls"] == 1
        payloads = [c["payload"] for c in fake_say.calls]
        assert TEMPLATE_NL_BUSY in payloads
        records = _read_audit_lines(audit_path)
        busy = [r for r in records if r.get("kind") == "nl_busy_rejected"]
        assert len(busy) == 1


# ---------------------------------------------------------------------------
# AC-NLS-3: turn 종료 후 새 NL 정상 처리
# ---------------------------------------------------------------------------


class TestNLSerializeSequential:
    def test_sequential_second_call_succeeds(
        self, sessions, fake_say, logger, audit_path
    ):
        runtime = _make_runtime(delay_s=0.0)
        event = {"client_msg_id": "key-s", "ts": "1.1", "channel": "D1"}

        _handle_natural_language(
            text="요약해줘",
            user_id="U0AE7A54NHL",
            event=event,
            say=fake_say,
            logger=logger,
            sessions=sessions,
            nl_runtime=runtime,
        )
        _handle_natural_language(
            text="다시 요약",
            user_id="U0AE7A54NHL",
            event={"client_msg_id": "key-s2", "ts": "1.2", "thread_ts": "1.1", "channel": "D1"},
            say=fake_say,
            logger=logger,
            sessions=sessions,
            nl_runtime=runtime,
        )

        assert runtime["state"]["sonnet_calls"] == 2
        # busy 거절은 발생하지 않았다.
        payloads = [c["payload"] for c in fake_say.calls]
        assert TEMPLATE_NL_BUSY not in payloads
        records = _read_audit_lines(audit_path)
        busy = [r for r in records if r.get("kind") == "nl_busy_rejected"]
        assert busy == []


# ---------------------------------------------------------------------------
# AC-NLS-4: structured 진행 중 NL — 별도 락이라 차단되지 않음
# ---------------------------------------------------------------------------


class TestNLSerializeStructuredCoexist:
    def test_structured_in_flight_does_not_block_nl(
        self, queue, sessions, fake_say, logger, audit_path
    ):
        """structured 분기 (`_handle_command` `STATUS`) 와 NL 분기는 별도 락.

        본 테스트는 직접 NL 분기를 호출해 SDK 호출이 정상 진행됨을 확인한다.
        structured 진행은 mock 으로 충분 — `JobQueue` 자체는 별 경로다.
        """
        runtime = _make_runtime(delay_s=0.0)
        rate_limiter = _RateLimiter()

        # structured (status) 명령 진행 — `_handle_command` fast-path.
        _handle_command(
            text="status",
            user_id="U0AE7A54NHL",
            event={"client_msg_id": "key-st", "ts": "1.0", "channel": "D1"},
            say=fake_say,
            logger=logger,
            queue=queue,
            rate_limiter=rate_limiter,
            sessions=sessions,
            nl_runtime=runtime,
        )
        # status 는 classifier 를 호출하지 않는다.
        assert runtime["state"]["classifier_calls"] == 0

        # NL 분기는 정상 진행 — 별도 락이라 차단 안 됨.
        _handle_natural_language(
            text="요약해줘",
            user_id="U0AE7A54NHL",
            event={"client_msg_id": "key-nl", "ts": "1.1", "channel": "D1"},
            say=fake_say,
            logger=logger,
            sessions=sessions,
            nl_runtime=runtime,
        )
        assert runtime["state"]["sonnet_calls"] == 1
        # busy 거절은 없다.
        payloads = [c["payload"] for c in fake_say.calls]
        assert TEMPLATE_NL_BUSY not in payloads


# ---------------------------------------------------------------------------
# AC-NLS-5: rate_limiter 가 먼저 발동 — busy 미발사
# ---------------------------------------------------------------------------


class TestNLSerializeRateLimitInterop:
    def test_rate_limit_fires_first_no_busy(
        self, queue, sessions, fake_say, logger, audit_path
    ):
        """`_RateLimiter` 가 먼저 발동하면 NL 분기 진입 자체가 안 되므로
        `TEMPLATE_NL_BUSY` 가 발사되지 않고 `nl_busy_rejected` audit 도 미기록.
        """
        runtime = _make_runtime(delay_s=0.0)
        rate_limiter = _RateLimiter()

        # 5초 윈도우 내 4건째 — rate limit 가 발동한다.
        for i in range(4):
            _handle_command(
                text="자연어 요약해줘",
                user_id="U0AE7A54NHL",
                event={"client_msg_id": f"k-{i}", "ts": f"{i}.0", "channel": "D1"},
                say=fake_say,
                logger=logger,
                queue=queue,
                rate_limiter=rate_limiter,
                sessions=sessions,
                nl_runtime=runtime,
            )

        payloads = [c["payload"] for c in fake_say.calls]
        # busy 안내는 절대 발사되지 않는다 — rate_limiter 가 먼저 차단.
        assert TEMPLATE_NL_BUSY not in payloads
        records = _read_audit_lines(audit_path)
        busy = [r for r in records if r.get("kind") == "nl_busy_rejected"]
        assert busy == []


# ---------------------------------------------------------------------------
# AC-NLS-6: audit `nl_busy_rejected` 1줄 기록 + 필드 정확히 4개
# ---------------------------------------------------------------------------


class TestNLSerializeAudit:
    def test_busy_audit_record_fields_exact(
        self, sessions, fake_say, logger, audit_path
    ):
        """busy 거절 1건 발생 시 audit 라인 필드가 정확히 `ts`/`kind`/`thread_ts`/`user_id_masked`
        4개여야 한다 (스키마 일관성).
        """
        runtime = _make_runtime(delay_s=0.3)

        event = {"client_msg_id": "key-1", "ts": "1.1", "channel": "D1"}

        def _invoke():
            _handle_natural_language(
                text="요약",
                user_id="U0AE7A54NHL",
                event=event,
                say=fake_say,
                logger=logger,
                sessions=sessions,
                nl_runtime=runtime,
            )

        t1 = threading.Thread(target=_invoke)
        t2 = threading.Thread(target=_invoke)
        t1.start()
        time.sleep(0.05)
        t2.start()
        t1.join(timeout=2.0)
        t2.join(timeout=2.0)

        records = _read_audit_lines(audit_path)
        busy = [r for r in records if r.get("kind") == "nl_busy_rejected"]
        assert len(busy) == 1
        rec = busy[0]
        # 필드 정확히 4개.
        assert set(rec.keys()) == {"ts", "kind", "thread_ts", "user_id_masked"}
        assert rec["kind"] == "nl_busy_rejected"
        assert rec["thread_ts"] == "1.1"
        # user_id 는 마스킹된 값.
        assert rec["user_id_masked"]
        assert rec["user_id_masked"] != "U0AE7A54NHL"


# ---------------------------------------------------------------------------
# AC-NLS-9: shutdown 보호 — 새 진입 거절, 진행 중 1건 graceful
# ---------------------------------------------------------------------------


class TestNLSerializeShutdown:
    def test_shutdown_flag_rejects_new_entry(
        self, sessions, fake_say, logger, audit_path
    ):
        """shutdown flag set 이후 새 NL 진입은 락 acquire 시도 이전에 즉시 거절."""
        runtime = _make_runtime(delay_s=0.0)
        main_mod._nl_shutdown_flag.set()

        _handle_natural_language(
            text="요약해줘",
            user_id="U0AE7A54NHL",
            event={"client_msg_id": "key-x", "ts": "1.1", "channel": "D1"},
            say=fake_say,
            logger=logger,
            sessions=sessions,
            nl_runtime=runtime,
        )
        # SDK 호출 0건.
        assert runtime["state"]["sonnet_calls"] == 0
        assert runtime["state"]["classifier_calls"] == 0
        # busy 안내 1줄.
        payloads = [c["payload"] for c in fake_say.calls]
        assert TEMPLATE_NL_BUSY in payloads
        # audit 라인 1줄.
        records = _read_audit_lines(audit_path)
        busy = [r for r in records if r.get("kind") == "nl_busy_rejected"]
        assert len(busy) == 1

    def test_in_flight_turn_completes_gracefully(
        self, sessions, fake_say, logger, audit_path
    ):
        """진행 중인 turn 은 shutdown flag set 이후에도 완수 (락 release 까지)."""
        runtime = _make_runtime(delay_s=0.3)

        results: dict[str, Any] = {}

        def _invoke():
            _handle_natural_language(
                text="요약해줘",
                user_id="U0AE7A54NHL",
                event={"client_msg_id": "key-i", "ts": "1.1", "channel": "D1"},
                say=fake_say,
                logger=logger,
                sessions=sessions,
                nl_runtime=runtime,
            )
            results["finished"] = True

        t = threading.Thread(target=_invoke)
        t.start()
        # 진행 중에 shutdown flag set.
        time.sleep(0.05)
        main_mod._nl_shutdown_flag.set()
        t.join(timeout=2.0)

        # 진행 중 1건은 graceful 완료.
        assert results.get("finished") is True
        assert runtime["state"]["sonnet_calls"] == 1
        # 락이 release 됐는지 — 새 acquire 가 성공해야 한다.
        acquired = main_mod._nl_turn_lock.acquire(blocking=False)
        assert acquired
        main_mod._nl_turn_lock.release()


# ---------------------------------------------------------------------------
# §7 위험 1번: 예외 발생 시 락 release (try/finally 검증)
# ---------------------------------------------------------------------------


class TestNLSerializeLockReleaseOnException:
    def test_lock_released_when_sonnet_raises(
        self, sessions, fake_say, logger, audit_path
    ):
        """`run_turn` 내부에서 예외가 발생해도 `try/finally` 가 락을 release 해야 한다.

        Sonnet 콜러블이 raise 하도록 구성. 함수 전체가 예외를 위로 throw 하지만
        락은 release 됐어야 한다 → 후속 acquire 가 즉시 성공.
        """

        def classifier(_sys, _user):
            return ClassificationResult(
                label=IntentLabel.SUMMARY_REQUEST,
                prompt_tokens=287,
                response_tokens=4,
            )

        def haiku(_text):
            return HaikuResponse(text="ok")

        def sonnet(_text, sid):
            raise RuntimeError("SDK boom")

        runtime = {
            "classifier": classifier,
            "haiku_responder": haiku,
            "sonnet_responder": sonnet,
        }

        with pytest.raises(RuntimeError, match="SDK boom"):
            _handle_natural_language(
                text="요약",
                user_id="U0AE7A54NHL",
                event={"client_msg_id": "key-e", "ts": "1.1", "channel": "D1"},
                say=fake_say,
                logger=logger,
                sessions=sessions,
                nl_runtime=runtime,
            )

        # 락이 release 됐는지 검증.
        acquired = main_mod._nl_turn_lock.acquire(blocking=False)
        assert acquired
        main_mod._nl_turn_lock.release()
