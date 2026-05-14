"""write 도구 명령 흐름 단위 테스트.

PRD: docs/prd/dev-relay-write-tools.md AC-WT-2 ~ AC-WT-13

검증 항목:
- AC-WT-2: structured `apply patch pr=N` 입력 → confirm 다이얼로그 발사.
- AC-WT-6: confirm `[취소]` → 작업 부작용 0.
- AC-WT-8: 동시성 — write 도구도 큐 적재 가드 통과.
- AC-WT-9: SDK 미가용 시 graceful 안내.
- AC-WT-10: shutdown flag set → 새 write 명령 거절.
- AC-WT-11: 멱등성 — 동일 client_msg_id 중복 시 큐 row 1건.
- AC-WT-12: rate limit — write 도구도 적용.
- AC-WT-13: audit log 완전성.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest import mock

import pytest

from ai.dev_relay.agent_sessions import AgentSessionStore
from ai.dev_relay.dispatcher import CommandKind, parse
from ai.dev_relay.main import _RateLimiter, _handle_command
from ai.dev_relay.queue import JobQueue


@pytest.fixture
def queue(tmp_path: Path) -> JobQueue:
    db = tmp_path / "queue.db"
    return JobQueue(db_path=db)


@pytest.fixture
def sessions(tmp_path: Path) -> AgentSessionStore:
    db = tmp_path / "queue.db"
    return AgentSessionStore(db_path=db)


@pytest.fixture
def fake_say():
    sent: list[Any] = []

    def _say(payload=None, *, blocks=None, text=None, **kwargs):
        if blocks is not None or text is not None:
            sent.append({"text": text, "blocks": blocks, **kwargs})
        else:
            sent.append(payload)

    _say.sent = sent  # type: ignore[attr-defined]
    return _say


@pytest.fixture
def logger():
    import logging
    return logging.getLogger("test_write_flow")


@pytest.fixture(autouse=True)
def isolate_audit(tmp_path: Path, monkeypatch):
    """audit.jsonl 경로 격리."""
    from ai.dev_relay import main as main_mod
    audit_path = tmp_path / "audit.jsonl"
    monkeypatch.setattr(main_mod, "_audit_log_path", lambda: audit_path)
    yield audit_path


@pytest.fixture(autouse=True)
def reset_shutdown(monkeypatch):
    """각 테스트마다 write shutdown flag 초기화."""
    from ai.dev_relay import main as main_mod
    import threading
    monkeypatch.setattr(
        main_mod, "_write_shutdown_flag", threading.Event()
    )
    monkeypatch.setattr(main_mod, "_write_pending", {})
    yield


# ---------------------------------------------------------------------------
# AC-WT-2: structured apply patch 진입 → SDK 가용 시 confirm 발사
# ---------------------------------------------------------------------------


class TestApplyPatchEntry:
    def test_apply_patch_dispatches_to_write_handler(
        self, queue, sessions, fake_say, logger
    ):
        """apply patch pr=N 입력 시 dispatcher 가 APPLY_PATCH_PR 로 분기."""
        cmd = parse("apply patch pr=22")
        assert cmd.kind is CommandKind.APPLY_PATCH_PR
        assert cmd.pr_number == 22

    def test_apply_patch_sdk_unavailable_graceful_notice(
        self, queue, sessions, fake_say, logger
    ):
        """SDK 미가용 시 SDK 인증 안내 1회 발사 (AC-WT-9)."""
        rate_limiter = _RateLimiter()
        with mock.patch(
            "ai.dev_relay.write_runtime.is_sdk_available", return_value=False
        ):
            _handle_command(
                text="apply patch pr=22",
                user_id="U0AE7A54NHL",
                event={"client_msg_id": "key-wt-1", "ts": "1.1", "channel": "D1"},
                say=fake_say,
                logger=logger,
                queue=queue,
                rate_limiter=rate_limiter,
                sessions=sessions,
                nl_runtime=None,
            )
        # SDK 미가용 안내 발사 — 큐 적재 안내 후 SDK 미가용 안내.
        # safe_say 는 단일 인자 호출이므로 sent 에 문자열로 들어간다.
        texts = [s for s in fake_say.sent if isinstance(s, str)]
        assert any("SDK 인증" in t for t in texts)


# ---------------------------------------------------------------------------
# AC-WT-10: shutdown flag set → 새 write 명령 즉시 거절
# ---------------------------------------------------------------------------


class TestWriteShutdownProtection:
    def test_shutdown_flag_rejects_new_apply_patch(
        self, queue, sessions, fake_say, logger
    ):
        from ai.dev_relay import main as main_mod
        main_mod._write_shutdown_flag.set()
        rate_limiter = _RateLimiter()
        _handle_command(
            text="apply patch pr=22",
            user_id="U0AE7A54NHL",
            event={"client_msg_id": "key-wt-sd", "ts": "1.1", "channel": "D1"},
            say=fake_say,
            logger=logger,
            queue=queue,
            rate_limiter=rate_limiter,
            sessions=sessions,
            nl_runtime=None,
        )
        texts = [s for s in fake_say.sent if isinstance(s, str)]
        # shutdown 안내 발사 확인.
        assert any("무효화" in t or "다시 명령" in t for t in texts)


# ---------------------------------------------------------------------------
# AC-WT-11: 멱등성 — 동일 client_msg_id 두 번 → 큐 1건
# ---------------------------------------------------------------------------


class TestWriteIdempotency:
    def test_duplicate_event_ignored(
        self, queue, sessions, fake_say, logger
    ):
        rate_limiter = _RateLimiter()
        with mock.patch(
            "ai.dev_relay.write_runtime.is_sdk_available", return_value=False
        ):
            for _ in range(2):
                _handle_command(
                    text="apply patch pr=22",
                    user_id="U0AE7A54NHL",
                    event={
                        "client_msg_id": "dup-key",
                        "ts": "1.1",
                        "channel": "D1",
                    },
                    say=fake_say,
                    logger=logger,
                    queue=queue,
                    rate_limiter=rate_limiter,
                    sessions=sessions,
                    nl_runtime=None,
                )
        # SQLite UNIQUE 제약으로 row 1건만 적재.
        from ai.dev_relay.queue import (
            STATUS_PENDING, STATUS_RUNNING, STATUS_DONE, STATUS_FAILED,
        )
        total = sum(
            queue.count_by_status(s)
            for s in (STATUS_PENDING, STATUS_RUNNING, STATUS_DONE, STATUS_FAILED)
        )
        assert total == 1


# ---------------------------------------------------------------------------
# AC-WT-12: rate limit — write 도구도 적용
# ---------------------------------------------------------------------------


class TestWriteRateLimit:
    def test_rate_limit_applies_to_write_commands(
        self, queue, sessions, fake_say, logger
    ):
        rate_limiter = _RateLimiter()
        # 3 건 성공 + 4 건째 차단 (limit=3).
        with mock.patch(
            "ai.dev_relay.write_runtime.is_sdk_available", return_value=False
        ):
            for i in range(4):
                _handle_command(
                    text="apply patch pr=22",
                    user_id="U0AE7A54NHL",
                    event={
                        "client_msg_id": f"key-rl-{i}",
                        "ts": "1.1",
                        "channel": "D1",
                    },
                    say=fake_say,
                    logger=logger,
                    queue=queue,
                    rate_limiter=rate_limiter,
                    sessions=sessions,
                    nl_runtime=None,
                )
        texts = [s for s in fake_say.sent if isinstance(s, str)]
        # rate limit 안내가 적어도 1회 발사.
        assert any("잠시" in t for t in texts)


# ---------------------------------------------------------------------------
# AC-WT-13: audit log 완전성
# ---------------------------------------------------------------------------


class TestWriteAuditCompleteness:
    def test_apply_patch_emits_requested_audit(
        self, queue, sessions, fake_say, logger, isolate_audit
    ):
        rate_limiter = _RateLimiter()
        with mock.patch(
            "ai.dev_relay.write_runtime.is_sdk_available", return_value=False
        ):
            _handle_command(
                text="apply patch pr=22",
                user_id="U0AE7A54NHL",
                event={"client_msg_id": "key-au-1", "ts": "1.1", "channel": "D1"},
                say=fake_say,
                logger=logger,
                queue=queue,
                rate_limiter=rate_limiter,
                sessions=sessions,
                nl_runtime=None,
            )
        # SDK 미가용 audit + command_received audit 기록 확인.
        import json
        lines = isolate_audit.read_text(encoding="utf-8").splitlines()
        records = [json.loads(line) for line in lines if line]
        kinds = [r.get("kind") for r in records]
        assert "command_received" in kinds
        assert "write_sdk_unavailable" in kinds
        # 모든 record 가 user_id_masked 키를 포함 (PR #50/#52 정책).
        for r in records:
            if r.get("kind") in ("command_received", "write_sdk_unavailable"):
                assert "user_id_masked" in r


# ---------------------------------------------------------------------------
# AC-WT-5: destructive 가드 — write 도구 명령에 destructive 표지
# ---------------------------------------------------------------------------


class TestWriteDestructiveGuard:
    @pytest.mark.parametrize(
        "text",
        [
            "apply patch pr=22 && push --force",
            "commit pr=22 --amend",
            "push pr=22 --force",
        ],
    )
    def test_destructive_text_rejected(
        self, queue, sessions, fake_say, logger, text
    ):
        rate_limiter = _RateLimiter()
        _handle_command(
            text=text,
            user_id="U0AE7A54NHL",
            event={
                "client_msg_id": f"key-dg-{hash(text) % 1000}",
                "ts": "1.1",
                "channel": "D1",
            },
            say=fake_say,
            logger=logger,
            queue=queue,
            rate_limiter=rate_limiter,
            sessions=sessions,
            nl_runtime=None,
        )
        texts = [s for s in fake_say.sent if isinstance(s, str)]
        # destructive 안내 발사 확인.
        assert any("PC에" in t or "직접" in t for t in texts)
