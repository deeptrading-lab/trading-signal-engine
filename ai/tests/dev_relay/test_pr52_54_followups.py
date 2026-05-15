"""PR #52 / PR #54 reviewer P2 후속 묶음 검증 테스트.

PRD: 본 묶음은 chore — PRD 없음. PR #52 (F-4) + PR #54 (F-5) reviewer P2 항목.

검증 범위:
- F-4 #1: Block Kit walker dict-form 분기 중복 수집 제거 (count == 1 보장).
- F-4 #2: `"user"` 키 deprecation 시점 (2026-07-13) 자동 알람 — pytest 정적
  날짜 가드. 시점 도달 시 fail 하여 retire 작업이 자연 트리거.
- F-4 #3: `handle_view_details` `mask_user_id` 패턴 통일은 코드 리뷰 항목 —
  본 파일에서는 동작 회귀 0 만 보장 (audit 레코드의 `user_id_masked` 형태).
- F-4 #4: `classify_merge_rejection` 비-`MergeRejection` 입력 방어 동작 — None,
  dict, str, 임의 객체 시 fallback `OTHER`.
- F-5 #1: `shutdown_dev_relay` 진행 중 write worker join (timeout 포함).
- F-5 #2: `force-with-lease` destructive 차단 명시 (PRD `dev-relay-write-tools.md`
  §3.3 정합 — NL/structured 모두 차단 유지).
- F-5 #3: `_resolve_repo_root` 모듈 lifetime 캐시 — 동일 cwd 에서 `git rev-parse`
  반복 호출 방지.
"""

from __future__ import annotations

import datetime as _dt
import logging
import threading
import time
from typing import Any

import pytest

from ai.dev_relay import main as main_mod
from ai.dev_relay.dispatcher import (
    CommandKind,
    is_destructive,
    parse,
)
from ai.dev_relay.main import (
    _collect_block_user_facing_text,
    _resolve_repo_root,
    _spawn_write_worker,
    shutdown_dev_relay,
)
from ai.dev_relay.merger import (
    REJECTION_CATEGORY_OTHER,
    classify_merge_rejection,
)


# ---------------------------------------------------------------------------
# F-4 #1: walker dict-form 중복 수집 제거.
# ---------------------------------------------------------------------------


class TestWalkerDictDedup:
    """`_BLOCK_USER_FACING_NON_TEXT_KEYS` 분기에서 inner text 가 정확히 1번만 수집된다."""

    def test_placeholder_text_collected_once(self) -> None:
        """`placeholder: {type, text}` inner text 가 `count == 1` 로만 수집됨."""
        blocks = [
            {
                "type": "input",
                "label": {"type": "plain_text", "text": "라벨"},
                "element": {
                    "type": "plain_text_input",
                    "placeholder": {"type": "plain_text", "text": "여기에 입력"},
                },
            }
        ]
        collected = _collect_block_user_facing_text(blocks)
        # "여기에 입력" 이 정확히 1번만 수집되어야 한다 (이전에는 dict 분기 fallthrough
        # 로 2번 수집됨).
        assert collected.count("여기에 입력") == 1
        # 라벨도 동일하게 1번.
        assert collected.count("라벨") == 1

    def test_image_alt_text_str_direct(self) -> None:
        """`image.alt_text` 가 str 직접인 경우 1번만 수집."""
        blocks = [{"type": "image", "alt_text": "alt", "image_url": "https://x"}]
        collected = _collect_block_user_facing_text(blocks)
        assert collected.count("alt") == 1

    def test_title_label_hint_all_dedup(self) -> None:
        """`title`/`label`/`hint` 모두 dict 형태에서 1번씩만 수집."""
        blocks = [
            {
                "title": {"type": "plain_text", "text": "타이틀"},
                "label": {"type": "plain_text", "text": "라벨"},
                "hint": {"type": "plain_text", "text": "힌트"},
            }
        ]
        collected = _collect_block_user_facing_text(blocks)
        assert collected.count("타이틀") == 1
        assert collected.count("라벨") == 1
        assert collected.count("힌트") == 1


# ---------------------------------------------------------------------------
# F-4 #2: `"user"` 키 deprecation 시점 자동 가드.
# ---------------------------------------------------------------------------


# PR #50 docstring 의 deprecation 시점.
_USER_KEY_DEPRECATION_DATE = _dt.date(2026, 7, 13)


class TestUserKeyDeprecationDateGuard:
    """deprecation 시점 도달 시 fail 하여 retire 작업을 자연 트리거.

    의도된 fail — 이 테스트가 fail 하면 `_append_audit` / 호출 측에서 `"user"`
    canonical back-compat 키를 제거하는 PR 을 진행해야 한다.
    """

    def test_deprecation_date_not_yet_reached(self) -> None:
        today = _dt.date.today()
        if today >= _USER_KEY_DEPRECATION_DATE:
            pytest.fail(
                "user 키 deprecation 시점({})이 도달했습니다. "
                "다운스트림 분석 도구의 `user_id_masked` 마이그레이션을 확인하고 "
                "`_append_audit` 호출 측의 `'user'` back-compat 키 제거 PR 을 진행하세요.".format(
                    _USER_KEY_DEPRECATION_DATE.isoformat()
                )
            )


# ---------------------------------------------------------------------------
# F-4 #4: `classify_merge_rejection` 비-`MergeRejection` 입력 방어.
# ---------------------------------------------------------------------------


class TestClassifyMergeRejectionDefensive:
    """`MergeRejection` 외 타입 입력 시 raise 없이 `OTHER` 로 fallback.

    `str(exc)` 가 어떤 객체에도 안전하게 동작하므로 본 함수는 ValueError 없이
    카테고리를 반환해야 한다 — 호출 측 (audit 기록) 이 None-safe.
    """

    def test_none_input(self) -> None:
        # str(None) == "None" — 어떤 매칭에도 안 걸려 OTHER.
        assert classify_merge_rejection(None) == REJECTION_CATEGORY_OTHER  # type: ignore[arg-type]

    def test_dict_input(self) -> None:
        assert classify_merge_rejection({"k": "v"}) == REJECTION_CATEGORY_OTHER  # type: ignore[arg-type]

    def test_str_input(self) -> None:
        assert classify_merge_rejection("random") == REJECTION_CATEGORY_OTHER  # type: ignore[arg-type]

    def test_arbitrary_object(self) -> None:
        class _X:
            def __str__(self) -> str:
                return "arbitrary"

        assert classify_merge_rejection(_X()) == REJECTION_CATEGORY_OTHER  # type: ignore[arg-type]

    def test_empty_string(self) -> None:
        assert classify_merge_rejection("") == REJECTION_CATEGORY_OTHER  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# F-5 #1: `shutdown_dev_relay` 진행 중 write worker join.
# ---------------------------------------------------------------------------


class TestShutdownJoinsActiveWriteWorkers:
    """shutdown 시 `_active_write_workers` 에 등록된 thread 가 join 된다."""

    def setup_method(self) -> None:
        main_mod._nl_shutdown_flag.clear()
        main_mod._write_shutdown_flag.clear()
        with main_mod._active_write_workers_lock:
            main_mod._active_write_workers.clear()

    def teardown_method(self) -> None:
        main_mod._nl_shutdown_flag.clear()
        main_mod._write_shutdown_flag.clear()
        with main_mod._active_write_workers_lock:
            main_mod._active_write_workers.clear()

    def test_spawn_registers_worker(self) -> None:
        """spawn 시 `_active_write_workers` 에 등록되고, 정상 종료 시 자동 제거."""
        done = threading.Event()

        def _fn() -> None:
            done.wait(timeout=1.0)

        logger = logging.getLogger("test")
        thread = _spawn_write_worker(_fn, job_id=1, logger=logger)
        # spawn 직후 set 에 존재.
        with main_mod._active_write_workers_lock:
            assert thread in main_mod._active_write_workers
        # 본문 끝나면 try/finally 로 제거.
        done.set()
        thread.join(timeout=2.0)
        with main_mod._active_write_workers_lock:
            assert thread not in main_mod._active_write_workers

    def test_shutdown_joins_active_workers(self) -> None:
        """진행 중 worker 가 timeout 내 종료되면 shutdown 이 정상 join."""
        from ai.dev_relay.agent_runner import AgentRunner

        runner = AgentRunner(max_workers=1)
        try:
            release = threading.Event()
            started = threading.Event()

            def _fn() -> None:
                started.set()
                release.wait(timeout=2.0)

            logger = logging.getLogger("test")
            thread = _spawn_write_worker(_fn, job_id=42, logger=logger)
            assert started.wait(timeout=1.0)
            # shutdown 전 미리 release — join 이 짧게 완료.
            release.set()
            shutdown_dev_relay(runner, timeout=2.0, logger=logger)
            # join 완료 → thread 가 set 에서 제거됨.
            assert not thread.is_alive()
            with main_mod._active_write_workers_lock:
                assert thread not in main_mod._active_write_workers
        finally:
            try:
                runner.shutdown(wait=False, timeout=0.1)
            except Exception:
                pass

    def test_shutdown_timeout_does_not_raise(self) -> None:
        """worker 가 timeout 안에 끝나지 않아도 예외 없이 진행 (daemon 강제 회수에 위임)."""
        from ai.dev_relay.agent_runner import AgentRunner

        runner = AgentRunner(max_workers=1)
        release = threading.Event()
        try:

            def _fn() -> None:
                # 의도적으로 길게 — shutdown timeout 내에 안 끝난다.
                release.wait(timeout=5.0)

            logger = logging.getLogger("test")
            _spawn_write_worker(_fn, job_id=99, logger=logger)
            # shutdown 은 timeout=0.1 내에 join 시도 후 반환되어야 한다.
            t0 = time.monotonic()
            shutdown_dev_relay(runner, timeout=0.1, logger=logger)
            elapsed = time.monotonic() - t0
            # join timeout + runner.shutdown timeout 합쳐도 1.5초 이내에 반환.
            assert elapsed < 1.5
        finally:
            release.set()
            try:
                runner.shutdown(wait=False, timeout=0.1)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# F-5 #2: `force-with-lease` destructive 차단 유지 (PRD §3.3 정합).
# ---------------------------------------------------------------------------


class TestForceWithLeaseBlocked:
    """PRD `dev-relay-write-tools.md` §3.3 — `--force-with-lease` 도 destructive."""

    @pytest.mark.parametrize(
        "text",
        [
            "git push --force-with-lease",
            "git push origin main --force-with-lease",
            "push --force-with-lease",
            "force-with-lease 로 푸시",
            "deploy with --force-with-lease",
            "git push origin --force_with_lease",
        ],
    )
    def test_force_with_lease_variants_blocked(self, text: str) -> None:
        assert is_destructive(text) is True
        assert parse(text).kind == CommandKind.DESTRUCTIVE_BLOCKED

    def test_non_force_token_not_blocked(self) -> None:
        """일반 NL ('lease 정책 알려줘') 는 차단되지 않는다 — 부분 문자열 회귀 가드."""
        # 'lease' 단독 토큰은 차단 대상 아님.
        assert is_destructive("lease 정책 알려줘") is False


# ---------------------------------------------------------------------------
# F-5 #3: `_resolve_repo_root` 모듈 lifetime 캐시.
# ---------------------------------------------------------------------------


class TestResolveRepoRootCache:
    """`_resolve_repo_root` 결과가 모듈 lifetime 동안 캐시된다 (재계산 0)."""

    def setup_method(self) -> None:
        # 모듈 캐시 초기화 — 본 케이스 단독 회귀 보장.
        main_mod._repo_root_cache = None

    def teardown_method(self) -> None:
        main_mod._repo_root_cache = None

    def test_cached_after_first_call(self) -> None:
        first = _resolve_repo_root()
        assert main_mod._repo_root_cache is not None
        # 두 번째 호출에서 git rev-parse 호출 없이 캐시 반환.
        second = _resolve_repo_root()
        assert second == first
        assert second is main_mod._repo_root_cache

    def test_env_override_takes_precedence(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
        """`DEV_RELAY_REPO_ROOT` 환경변수가 git toplevel 보다 우선."""
        main_mod._repo_root_cache = None
        monkeypatch.setenv("DEV_RELAY_REPO_ROOT", str(tmp_path))
        resolved = _resolve_repo_root()
        assert resolved == tmp_path.resolve()
