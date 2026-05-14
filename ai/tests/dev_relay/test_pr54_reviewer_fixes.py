"""PR #54 reviewer 후속 fix 검증 테스트.

PRD: docs/prd/dev-relay-write-tools.md
PR #54 reviewer 코멘트 항목:
- P0: write 명령 SDK 호출 worker thread 패턴 (Slack 3초 timeout 보호).
- P1 #1: write_tools cwd 명시 주입.
- P1 #2: dispatcher destructive 단독 토큰 매치 (NL false-positive 방지).
- P1 #3: write_runtime 모델 ID 공유 상수 사용 (DRY).
- P1 #4: `_handle_write_command` docstring 정합성 (P0 fix 의 부산물).
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any
from unittest import mock

import pytest


# ---------------------------------------------------------------------------
# P1 #2: dispatcher destructive 단독 토큰 매치
# ---------------------------------------------------------------------------


class TestDispatcherDestructiveTokenMatch:
    """`--force`/`--amend`/`--no-verify` 가 단독 토큰일 때만 차단.

    부분 문자열 매치 시 정상 NL 메시지가 잘못 차단되던 회귀를 방지한다.
    """

    @pytest.mark.parametrize(
        "text",
        [
            "git push origin main --force",  # 단독 토큰
            "fix --no-verify HEAD",
            "commit --amend",
            "deploy with --force-with-lease",
        ],
    )
    def test_flag_as_single_token_is_destructive(self, text: str):
        from ai.dev_relay.dispatcher import is_destructive
        assert is_destructive(text) is True

    @pytest.mark.parametrize(
        "text",
        [
            "amend 정책 알려줘",
            "force 옵션이 왜 위험한가요",
            "noverify 가 정확히 뭐지",
            "force 라는 단어가 들어간 명령은 무엇이 있나요",
            "amend 와 fixup 차이가 뭔가요",
        ],
    )
    def test_substring_only_is_not_destructive(self, text: str):
        """flag 토큰이 단어 일부로 등장하면 destructive 가 아니다 (NL 통과).

        참고: `force-push`/`force_with_lease` 같은 시퀀스 표지는 destructive intent
        가 명확해 차단 유지. 본 테스트는 flag 단독 토큰의 부분 매치 false-positive
        만 회귀 방지.
        """
        from ai.dev_relay.dispatcher import is_destructive
        assert is_destructive(text) is False, (
            f"NL false-positive: '{text}' 가 destructive 로 잘못 분류됨"
        )

    def test_sequence_patterns_still_blocked(self):
        """기존 시퀀스 표지(`reset --hard`, `push --force` 등) 는 그대로 차단."""
        from ai.dev_relay.dispatcher import is_destructive
        assert is_destructive("git reset --hard HEAD~5") is True
        assert is_destructive("git push --force origin main") is True
        assert is_destructive("rm -rf docs") is True

    def test_branch_delete_pair_blocked(self):
        """`branch -D` / `branch -d` 페어 매치."""
        from ai.dev_relay.dispatcher import is_destructive
        assert is_destructive("git branch -D feature/foo") is True
        assert is_destructive("git branch -d feature/foo") is True

    def test_branch_alone_not_blocked(self):
        """`branch` 단독은 차단 대상 아님."""
        from ai.dev_relay.dispatcher import is_destructive
        assert is_destructive("git branch") is False
        assert is_destructive("branch 전환 방법 알려줘") is False


# ---------------------------------------------------------------------------
# P1 #1: write_tools cwd 주입 검증
# ---------------------------------------------------------------------------


class TestWriteToolsCwdInjection:
    """`apply_patch`/`perform_commit`/`perform_push`/`preview_commit`/`preview_push`
    가 cwd 인자를 호출 측에서 받아 subprocess 에 그대로 전달하는지 검증.

    PR #54 reviewer P1 #1 후속 — runner 미주입 (실 subprocess) 경로에서 cwd 누락
    은 명시 에러로 거절.
    """

    SAMPLE_PATCH = (
        "--- a/foo.py\n+++ b/foo.py\n@@ -1 +1 @@\n-old\n+new\n"
    )

    def test_apply_patch_propagates_cwd(self):
        from ai.dev_relay.write_tools import apply_patch
        calls: list[dict] = []

        def runner(args, **kwargs):
            calls.append({"args": tuple(args), "cwd": kwargs.get("cwd")})

            class _R:
                returncode = 0
                stdout = ""
                stderr = ""
            return _R()

        applied = apply_patch(self.SAMPLE_PATCH, cwd="/tmp/some-repo", runner=runner)
        assert applied == ("foo.py",)
        # 모든 subprocess 호출이 동일한 cwd 를 받아야 한다.
        for c in calls:
            assert c["cwd"] == "/tmp/some-repo", f"cwd 누락: {c}"

    def test_perform_commit_propagates_cwd(self):
        from ai.dev_relay.write_tools import perform_commit
        calls: list[dict] = []

        def runner(args, **kwargs):
            calls.append({"args": tuple(args), "cwd": kwargs.get("cwd")})

            class _R:
                returncode = 0
                stdout = "abcdef1234567890\n" if "rev-parse" in args else ""
                stderr = ""
            return _R()

        sha = perform_commit("개선 반영", cwd="/tmp/some-repo", runner=runner)
        assert sha == "abcdef123456"
        for c in calls:
            assert c["cwd"] == "/tmp/some-repo"

    def test_perform_push_propagates_cwd(self):
        from ai.dev_relay.write_tools import perform_push
        calls: list[dict] = []

        def runner(args, **kwargs):
            calls.append({"args": tuple(args), "cwd": kwargs.get("cwd")})

            class _R:
                returncode = 0
                stdout = "feature/foo\n" if "branch" in args else ""
                stderr = ""
            return _R()

        remote, branch = perform_push(cwd="/tmp/some-repo", runner=runner)
        assert remote == "origin"
        assert branch == "feature/foo"
        for c in calls:
            assert c["cwd"] == "/tmp/some-repo"

    def test_preview_commit_propagates_cwd(self):
        from ai.dev_relay.write_tools import preview_commit
        calls: list[dict] = []

        def runner(args, **kwargs):
            calls.append({"args": tuple(args), "cwd": kwargs.get("cwd")})

            class _R:
                returncode = 0
                stdout = "ai/foo.py\n"
                stderr = ""
            return _R()

        preview = preview_commit(
            "개선 반영", cwd="/tmp/some-repo", runner=runner, auto_stage=False
        )
        assert preview.message == "개선 반영"
        for c in calls:
            assert c["cwd"] == "/tmp/some-repo"

    def test_preview_push_propagates_cwd(self):
        from ai.dev_relay.write_tools import preview_push
        calls: list[dict] = []

        def runner(args, **kwargs):
            calls.append({"args": tuple(args), "cwd": kwargs.get("cwd")})

            class _R:
                returncode = 0
                stdout = "feature/foo\n" if "branch" in args else "abc123\n"
                stderr = ""
            return _R()

        preview = preview_push(cwd="/tmp/some-repo", runner=runner)
        assert preview.branch == "feature/foo"
        for c in calls:
            assert c["cwd"] == "/tmp/some-repo"


# ---------------------------------------------------------------------------
# P1 #3: write_runtime 모델 ID 공유 상수 사용
# ---------------------------------------------------------------------------


class TestWriteRuntimeModelIdShared:
    """`write_runtime` 이 `nl_classifier` 모델 ID 상수를 재사용하는지 검증.

    소스 텍스트에서 하드코딩된 모델 ID 리터럴이 사라졌고, `MODEL_SONNET_ID`/
    `MODEL_HAIKU_ID` 가 import 되었는지 검사.
    """

    def test_no_hardcoded_model_ids(self):
        path = Path(__file__).resolve().parents[3] / "ai" / "dev_relay" / "write_runtime.py"
        source = path.read_text(encoding="utf-8")
        # 모델 ID 리터럴이 코드 안에 직접 등장하지 않아야 한다 (system prompt
        # 본문이나 docstring 도 동일).
        assert '"claude-sonnet-4-6"' not in source, (
            "write_runtime.py 에 하드코딩된 sonnet 모델 ID 가 남아 있음"
        )
        assert '"claude-haiku-4-5-20251001"' not in source, (
            "write_runtime.py 에 하드코딩된 haiku 모델 ID 가 남아 있음"
        )

    def test_imports_shared_constants(self):
        from ai.dev_relay import write_runtime
        from ai.dev_relay.nl_classifier import MODEL_HAIKU_ID, MODEL_SONNET_ID
        # 두 모듈이 동일한 상수 값을 참조하는지 확인.
        assert write_runtime.MODEL_SONNET_ID == MODEL_SONNET_ID
        assert write_runtime.MODEL_HAIKU_ID == MODEL_HAIKU_ID


# ---------------------------------------------------------------------------
# P0 + P1 #4: write 명령 worker thread 패턴
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_audit(tmp_path: Path, monkeypatch):
    from ai.dev_relay import main as main_mod
    audit_path = tmp_path / "audit.jsonl"
    monkeypatch.setattr(main_mod, "_audit_log_path", lambda: audit_path)
    yield audit_path


@pytest.fixture
def reset_write_state(monkeypatch):
    from ai.dev_relay import main as main_mod
    import threading as _t
    monkeypatch.setattr(main_mod, "_write_shutdown_flag", _t.Event())
    monkeypatch.setattr(main_mod, "_write_pending", {})
    yield


class TestWriteCommandWorkerPattern:
    """write 명령 진입 시 SDK 호출이 worker thread 로 위임되는지 검증.

    회귀 시나리오: SDK 호출이 메시지 핸들러 thread 에서 블록되면 Slack 3초 timeout
    위반. worker 패턴이 적용되면 핸들러는 즉시 반환하고 SDK 응답은 별도 thread 에서
    confirm 다이얼로그 발사 시점에 도착.
    """

    def test_spawn_write_worker_runs_callback_async(self, monkeypatch, isolated_audit, reset_write_state):
        """`_spawn_write_worker` 가 daemon thread 를 즉시 spawn 하고 callback 실행."""
        import logging
        from ai.dev_relay.main import _spawn_write_worker
        completed = []

        def _fn():
            completed.append("done")

        thread = _spawn_write_worker(
            _fn, job_id=999, logger=logging.getLogger("test")
        )
        assert thread.daemon is True
        # daemon thread 이므로 join 으로 완료 대기.
        thread.join(timeout=2.0)
        assert not thread.is_alive()
        assert completed == ["done"]

    def test_handle_write_command_returns_quickly_when_sdk_call_slow(
        self, monkeypatch, isolated_audit, reset_write_state
    ):
        """SDK 호출이 느려도 `_handle_write_command` 는 worker 로 위임 후 즉시 반환.

        시나리오: `_build_and_send_write_confirm` 이 1초 sleep 하도록 monkeypatch.
        `_handle_write_command` 호출이 0.3초 이내에 반환해야 한다 (3초 timeout 보호).
        """
        import logging
        from ai.dev_relay import main as main_mod

        sent: list[Any] = []

        def _say(payload=None, *, blocks=None, text=None, **kwargs):
            sent.append(payload if payload is not None else {"text": text, "blocks": blocks})

        # SDK 가 가용한 것으로 가장.
        monkeypatch.setattr(
            "ai.dev_relay.write_runtime.is_sdk_available", lambda: True
        )

        # _build_and_send_write_confirm 을 느린 mock 으로 교체.
        worker_started = []
        worker_finished = []

        def _slow_build(**kwargs):
            worker_started.append(time.monotonic())
            time.sleep(0.5)  # SDK 응답 지연 시뮬레이션
            worker_finished.append(time.monotonic())

        monkeypatch.setattr(main_mod, "_build_and_send_write_confirm", _slow_build)

        from ai.dev_relay.dispatcher import CommandKind

        t0 = time.monotonic()
        main_mod._handle_write_command(
            kind=CommandKind.APPLY_PATCH_PR,
            pr_number=22,
            idempotency_key="key-worker-1",
            job_id=42,
            event={"client_msg_id": "key-worker-1", "ts": "1.1", "channel": "D1"},
            user_id="U0AE7A54NHL",
            say=_say,
            logger=logging.getLogger("test_worker"),
        )
        elapsed = time.monotonic() - t0

        # 메시지 핸들러는 0.3초 이내 반환 (worker 의 0.5초 sleep 을 안 기다림).
        assert elapsed < 0.3, (
            f"_handle_write_command 가 worker 완료까지 블록됨 ({elapsed:.2f}s)"
        )

        # 첫 응답(queue accepted) 은 동기 발사되어야 한다.
        text_sent = [s for s in sent if isinstance(s, str)]
        assert any("PR #22" in t or "패치" in t for t in text_sent), (
            "큐 적재 안내가 동기 발사되지 않음"
        )

        # worker 가 spawn 되어 실행 시작했는지 확인 (background 진행 중).
        deadline = time.monotonic() + 2.0
        while not worker_started and time.monotonic() < deadline:
            time.sleep(0.02)
        assert worker_started, "worker thread 가 spawn 되지 않음"

        # 정리: worker 완료 대기.
        while not worker_finished and time.monotonic() < deadline:
            time.sleep(0.02)

    def test_handle_write_command_docstring_mentions_worker(self):
        """`_handle_write_command` docstring 이 worker 패턴을 명시한다.

        PR #54 reviewer P1 #4 회귀 방지 — docstring 과 실제 동작 정합성.
        """
        from ai.dev_relay.main import _handle_write_command
        doc = _handle_write_command.__doc__ or ""
        assert "worker" in doc.lower() or "daemon" in doc.lower(), (
            "docstring 에 worker thread 위임이 명시되지 않음"
        )


# ---------------------------------------------------------------------------
# 통합: NL false-positive 감소 + dispatcher 라우팅 회귀
# ---------------------------------------------------------------------------


class TestNlFriendlyDestructiveBoundary:
    """NL 분기로 흐를 메시지가 destructive 로 잘못 분류되지 않는지 통합 검증."""

    @pytest.mark.parametrize(
        "text",
        [
            "amend 가 뭔가요",
            "force 옵션 설명해줘",
            "noverify 무슨 뜻이지",
        ],
    )
    def test_nl_query_routes_to_unknown_not_destructive(self, text: str):
        from ai.dev_relay.dispatcher import CommandKind, parse
        cmd = parse(text)
        # NL 분기로 흐를 수 있도록 UNKNOWN 으로 라우팅되어야 한다.
        assert cmd.kind is CommandKind.UNKNOWN, (
            f"NL 라우팅 차단: '{text}' → {cmd.kind}"
        )
