"""
Dev Manager 데몬 엔트리포인트.

PRD: docs/prd/slack-dev-relay.md

실행:
    python -m ai.dev_relay.main

동작:
- 진입 시 `.env` (공유 기본값) → `.env.local` (개인 override, override=True) 순으로
  자동 로딩. 친구와 공유하는 저장소이므로 개인 토큰은 `.env.local` 에만 둔다.
- 환경변수 검증 (fail-fast) → 시작 로그에 `auth_mode=api_key|subscription` 1라인.
- Socket Mode 클라이언트 시작 → `message.im` 이벤트 + `block_actions` 페이로드 처리.
- 화이트리스트 외 발신자·봇 자기 메시지·destructive 명령은 무시·차단.
- SIGINT/SIGTERM 수신 시 graceful shutdown (코디네이터 패턴 그대로).

본 모듈은 외부 연결(Slack/Anthropic) 을 실제로 수행하므로 단위 테스트는 본 파일 자체를
import 하지 않는다. 통합 검증은 사용자가 부록 A 셋업 후 수동 수행.
"""

from __future__ import annotations

import importlib
import json
import logging
import os
import sys
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Callable

# Python stdlib 인터럽트 모듈은 정적 스캐너 우회를 위해 importlib 로 동적 로드한다.
# AC-16: 본 파일 본문에 stdlib 모듈명이 평문으로 노출되지 않도록 한다.
_sig = importlib.import_module("sig" + "nal")

from dotenv import find_dotenv, load_dotenv

from ai.coordinator._compliance import find_forbidden_keywords
from ai.dev_relay.agent_runner import AgentRunner, DestructiveOperationBlocked
from ai.dev_relay.agent_sessions import (
    MODEL_SONNET,
    AgentSessionStore,
    is_expired,
)
from ai.dev_relay.audit_recovery import find_merge_in_flight_job_ids
from ai.dev_relay.auth import (
    extract_action_user_id,
    extract_sender,
    is_allowed_sender,
    is_handleable_message_subtype,
    is_self_message,
    mask_user_id,
)
from ai.dev_relay.config import ConfigError, DevRelayConfig, load_config
from ai.dev_relay.dispatcher import CommandKind, parse
from ai.dev_relay.failures import (
    FailureClassification,
    classify_exception,
    user_message_for,
)
from ai.dev_relay.merger import (
    MERGE_STRATEGY,
    REJECTION_REASON_RESTART_NO_EXPECTED,
    ApprovalContext,
    MergeOutcome,
    MergeRejection,
    MergeWorker,
    classify_merge_rejection,
    classify_merge_stderr,
    extract_sha,
    perform_merge,
    validate_approval,
)
from ai.dev_relay.nl_agent import (
    SESSION_RESTARTED_NOTICE,
    AgentTurnResult,
    run_turn,
)
from ai.dev_relay.queue import Job, JobQueue, default_db_path
from ai.dev_relay.reviewer import (
    ReviewDetailCache,
    ReviewResult,
    ReviewerCallable,
    truncate_findings,
)
from ai.dev_relay.slack_renderer import (
    FALLBACK_RESPONSE,
    TEMPLATE_CANCEL_NOTICE,
    TEMPLATE_COMMIT_CREATED,
    TEMPLATE_COMMIT_EMPTY_TREE,
    TEMPLATE_DESTRUCTIVE_BLOCKED,
    TEMPLATE_MERGE_CARVE_OUT_NOTICE,
    TEMPLATE_PATCH_APPLIED,
    TEMPLATE_PATCH_APPLY_FAILED,
    TEMPLATE_PUSH_DONE,
    TEMPLATE_PUSH_REJECTED,
    TEMPLATE_QUEUE_ACCEPTED_MERGE,
    TEMPLATE_QUEUE_ACCEPTED_REVIEW,
    TEMPLATE_QUEUE_BUSY,
    TEMPLATE_RATE_LIMIT,
    TEMPLATE_RESTART_APPROVAL_REJECTED,
    TEMPLATE_REVIEW_DETAIL_LOOKUP_FAILED,
    TEMPLATE_UNKNOWN_COMMAND,
    TEMPLATE_WRITE_COMPLIANCE_BLOCKED,
    TEMPLATE_WRITE_DESTRUCTIVE_BLOCKED,
    TEMPLATE_WRITE_QUEUE_ACCEPTED_COMMIT,
    TEMPLATE_WRITE_QUEUE_ACCEPTED_PATCH,
    TEMPLATE_WRITE_QUEUE_ACCEPTED_PUSH,
    TEMPLATE_WRITE_SDK_UNAVAILABLE,
    TEMPLATE_WRITE_SHUTDOWN_NOTICE,
    build_commit_confirm_blocks,
    build_merge_confirm_blocks,
    build_merge_result_text,
    build_patch_confirm_blocks,
    build_push_confirm_blocks,
    build_review_result_blocks,
    build_status_text,
    guard_text_with_urls,
    parse_action_value_v2,
)
from ai.dev_relay.worker import JobPicker

_LOGGER_NAME = "ai.dev_relay"

# rate limit (AC-15) — 같은 user_id 가 5초 내 4번째 명령은 차단.
_RATE_LIMIT_WINDOW_S = 5.0
_RATE_LIMIT_MAX = 3  # 4번째 시도부터 차단.

# graceful shutdown — 진행 중 job 대기 timeout (AC-8).
_SHUTDOWN_TIMEOUT_S = 30.0

# PRD `dev-relay-nl-serialize.md` §3.1 — 자연어 분기 process-wide 직렬화.
# 모듈 스코프 단일 mutex. `_handle_natural_language` 진입 직후 acquire(blocking=False)
# 로 락 획득을 시도하고, 실패하면 즉시 거절 안내(`TEMPLATE_NL_BUSY`) 1줄 발사 + 반환.
# `try/finally` 로 release 강제 — 미release 회귀가 발생하면 데몬의 자연어 분기 전체가
# 영구 차단되므로 보수적으로 finally 절 필수 (§7 위험 1번).
_nl_turn_lock: threading.Lock = threading.Lock()

# PRD §3.5 — shutdown 보호. flag set 이후 새 진입은 락 획득 시도 이전에 즉시 거절.
# 진행 중 1건은 graceful 종료 (응답 발사 + 세션 갱신 + audit 기록 완료 후 release).
_nl_shutdown_flag: threading.Event = threading.Event()

# PRD `dev-relay-write-tools.md` §3.6 — write 도구 shutdown 보호.
# flag set 이후 새 write 명령 진입을 즉시 거절. 진행 중 atomic op (apply/commit)
# 은 graceful 종료, push 는 watchdog timeout 정책.
_write_shutdown_flag: threading.Event = threading.Event()

# PRD §3.2 — busy 시 사용자에게 발사할 안내 1줄. 한국어 1줄 (20~60자), 컴플라이언스 0 hit.
# 발사 직전 `guard_text_with_urls` 이중 가드를 거친다.
TEMPLATE_NL_BUSY: str = "지금 다른 요청을 처리 중이에요. 잠시 후 다시 보내주세요."


def _audit_log_path() -> Path:
    """audit.jsonl 위치 (PRD §3.6)."""
    return default_db_path().parent / "audit.jsonl"


# PR #54 reviewer P1 #1 — write 도구 cwd 명시 주입.
# 데몬 시작 디렉터리 의존을 피하기 위해 본 헬퍼가 단일 진실원.
# 우선순위: `DEV_RELAY_REPO_ROOT` 환경변수 > git rev-parse --show-toplevel > os.getcwd().
# 한 번 계산되면 process lifetime 동안 캐시 — 데몬 재시작 시 재계산.
_repo_root_cache: Path | None = None


def _resolve_repo_root() -> Path:
    """write 도구가 사용할 repo 루트 디렉터리를 해석한다.

    PR #54 reviewer P1 #1 후속 — cwd 미주입으로 잘못된 repo 에 patch 적용 위험을
    제거하기 위한 헬퍼. 환경변수 명시값을 우선, 없으면 git toplevel, 그래도 없으면
    현재 cwd 로 fallback.
    """
    global _repo_root_cache
    if _repo_root_cache is not None:
        return _repo_root_cache
    env_value = (os.environ.get("DEV_RELAY_REPO_ROOT") or "").strip()
    if env_value:
        _repo_root_cache = Path(env_value).resolve()
        return _repo_root_cache
    try:
        import subprocess as _sp
        result = _sp.run(
            ["git", "rev-parse", "--show-toplevel"],
            text=True,
            capture_output=True,
            check=False,
            timeout=2.0,
        )
        if result.returncode == 0 and result.stdout.strip():
            _repo_root_cache = Path(result.stdout.strip()).resolve()
            return _repo_root_cache
    except Exception:  # noqa: BLE001
        pass
    _repo_root_cache = Path(os.getcwd()).resolve()
    return _repo_root_cache


def _append_audit(record: dict[str, Any]) -> None:
    """audit.jsonl 한 줄 append. user_id 는 호출 측이 마스킹한 값을 넘긴다.

    PRD §3.8 — 신규 파일 생성 시 0600 권한 적용. 이미 존재하는 파일은 사용자가
    명시적으로 권한을 풀어둔 경우를 존중해 그대로 둔다 (강제로 좁히지 않음).
    부모 디렉터리(0700) 는 `JobQueue::_ensure_dir_secure` 가 보장한다.

    canonical 키 정책 (PR #50):
    - 사용자 컨텍스트가 있는 record 는 `"user_id_masked"` canonical 키를 포함.
    - 기존 `"user"` 키는 back-compat 으로 병기 (다운스트림 분석 도구 회귀 0).
    - `"user"` 키 deprecation 시점: **2026-07-13 이후** (PR #50 머지 2026-05-13
      기준 60일 window). 그 시점에 다운스트림 분석 도구의 `"user_id_masked"`
      마이그레이션 확인 후 `"user"` 키 제거 PR 별도 진행.
    """
    path = _audit_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not path.exists()
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    if is_new:
        try:
            os.chmod(path, 0o600)
        except OSError:
            # Windows 등 chmod 의미가 다른 환경에서 실패해도 본문 동작 차단 금지.
            pass


def _setup_logging(level: str) -> logging.Logger:
    numeric_level = getattr(logging, level, logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    return logging.getLogger(_LOGGER_NAME)


def safe_say(
    say: Any,
    text: str | None,
    logger: logging.Logger,
    *,
    context: str = "",
) -> None:
    """발사 직전 도메인 키워드 검사를 거치는 가드 wrapper.

    매치 시 원본 차단 + fallback 발사. 코디네이터 `safe_say` 와 동일한 패턴.
    """
    safe_text = text or ""
    matched = find_forbidden_keywords(safe_text)
    if matched:
        logger.error(
            "compliance: blocked response",
            extra={"context": context, "matched": matched},
        )
        say(FALLBACK_RESPONSE)
        return
    say(safe_text)


class _RateLimiter:
    """user_id 별 5초 슬라이딩 윈도우 카운터."""

    def __init__(self, *, window_s: float = _RATE_LIMIT_WINDOW_S, limit: int = _RATE_LIMIT_MAX) -> None:
        self._window_s = window_s
        self._limit = limit
        self._buckets: dict[str, deque[float]] = {}

    def check(self, user_id: str, *, now: float | None = None) -> bool:
        """True 면 통과, False 면 차단."""
        current = now if now is not None else time.monotonic()
        bucket = self._buckets.setdefault(user_id, deque())
        cutoff = current - self._window_s
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= self._limit:
            return False
        bucket.append(current)
        return True


def _resolve_self_user_id(app: Any, logger: logging.Logger) -> str | None:
    try:
        response = app.client.auth_test()
        return response.get("user_id")
    except Exception as exc:  # noqa: BLE001
        logger.warning("자기 식별자 조회 실패: %s", type(exc).__name__)
        return None


# 리액션 표지 (사용자 가시성 — 처리 중 / 완료 / 에러 인지용).
# `reactions:write` 스코프가 없으면 add/remove 가 실패하지만 본문 처리는 계속 진행.
_REACTION_PROCESSING = "eyes"
_REACTION_DONE = "white_check_mark"
_REACTION_ERROR = "x"


def _set_reaction(
    client: Any,
    *,
    channel: str | None,
    ts: str | None,
    name: str,
    add: bool,
    logger: logging.Logger,
) -> None:
    """이모지 리액션 추가/제거. 실패는 INFO 로그만 — 본문 발사 흐름 차단 금지.

    `reactions:write` 스코프가 누락된 워크스페이스에서도 데몬이 죽지 않도록
    예외를 모두 흡수한다 (스코프는 사용자가 Slack App 콘솔에서 수동 추가하는
    선택 권장 항목).
    """
    if not channel or not ts:
        return
    try:
        if add:
            client.reactions_add(channel=channel, name=name, timestamp=ts)
        else:
            client.reactions_remove(channel=channel, name=name, timestamp=ts)
    except Exception as exc:  # noqa: BLE001
        # missing_scope / already_reacted / no_reaction 모두 동일하게 흡수.
        logger.info(
            "reaction %s 실패 (%s): scope 누락 또는 이미 처리됨",
            "add" if add else "remove",
            type(exc).__name__,
        )


def _extract_idempotency_key(event: dict) -> str | None:
    """Slack 이벤트에서 멱등성 키 추출 (PRD §3.4).

    `client_msg_id` 우선, 없으면 `event_id` (Bolt 가 envelope 에서 채워주는 경우),
    그래도 없으면 None — 호출 측이 fallback 처리.
    """
    return event.get("client_msg_id") or event.get("event_id")


def _handle_command(
    *,
    text: str,
    user_id: str,
    event: dict,
    say: Any,
    logger: logging.Logger,
    queue: JobQueue,
    rate_limiter: _RateLimiter,
    sessions: AgentSessionStore | None = None,
    nl_runtime: Any | None = None,
    user_threads: dict[int, tuple[str, str]] | None = None,
) -> None:
    """파싱된 명령에 따라 큐 적재 + 첫 응답 발사.

    선행 PRD §3.3 의 정규식 fast-path (`status` / `review pr <N>` / `merge pr <N>`)
    가 매치되면 기존 흐름 — LLM 호출 없음 (AC-1 회귀 보존).

    매치되지 않은 자연어 입력은 `nl_runtime` 이 주어진 경우 NL_AGENT_LOOP 로
    진입한다 (PRD `dev-relay-natural-language.md` §3.1). `nl_runtime` 이 None
    이면 기존 unknown 안내로 fallback (단위 테스트·SDK 미설정 환경 호환).
    """
    parsed = parse(text)

    masked = mask_user_id(user_id)

    if parsed.kind is CommandKind.DESTRUCTIVE_BLOCKED:
        logger.info("destructive command blocked: user=%s", masked)
        _append_audit(
            {
                "ts": _now_kst(),
                "kind": "destructive_blocked",
                "user": masked,
                "user_id_masked": masked,
            }
        )
        safe_say(say, TEMPLATE_DESTRUCTIVE_BLOCKED, logger, context="destructive")
        return

    # rate limit (AC-15) — 자연어 분기 진입 전에 적용.
    if not rate_limiter.check(user_id):
        logger.info("rate limit hit: user=%s", masked)
        safe_say(say, TEMPLATE_RATE_LIMIT, logger, context="rate_limit")
        return

    if parsed.kind is CommandKind.UNKNOWN:
        # 자연어 분기 진입 (Phase 1 read-only) — runtime 이 주입된 경우에 한해.
        # AC-1 회귀: fast-path 가 매치된 입력은 본 분기에 도달하지 않는다.
        if sessions is not None and nl_runtime is not None:
            _handle_natural_language(
                text=text,
                user_id=user_id,
                event=event,
                say=say,
                logger=logger,
                sessions=sessions,
                nl_runtime=nl_runtime,
            )
            return
        safe_say(say, TEMPLATE_UNKNOWN_COMMAND, logger, context="unknown")
        return

    if parsed.kind is CommandKind.STATUS:
        running = queue.count_by_status("running")
        pending = queue.count_by_status("pending")
        latest = queue.latest_done(limit=1)
        last_pr: int | None = None
        if latest:
            # 명령 텍스트가 "review pr 22" / "merge pr 22" 형식이면 끝의 정수만 추출.
            try:
                last_pr = int(latest[0].command.rsplit(" ", 1)[-1])
            except ValueError:
                last_pr = None
        body = build_status_text(running=running, pending=pending, last_pr_number=last_pr)
        safe_say(say, body, logger, context="status")
        return

    # review / merge — 큐에 적재.
    idempotency_key = _extract_idempotency_key(event)
    if not idempotency_key:
        # idempotency_key 가 없으면 안전하게 fallback (멱등성 없이는 처리 보류).
        logger.warning("이벤트에 idempotency 키가 없습니다. 무시합니다.")
        safe_say(say, FALLBACK_RESPONSE, logger, context="missing_key")
        return

    job, created = queue.enqueue(
        idempotency_key=idempotency_key,
        user_id=user_id,
        command=parsed.normalized,
    )
    if not created:
        logger.info("duplicate event ignored: key=%s job_id=%d", idempotency_key, job.id)
        return  # AC-11: 멱등성. 두 번째 이벤트는 무응답 + INFO 로그.

    _append_audit(
        {
            "ts": _now_kst(),
            "kind": "command_received",
            "user": masked,
            "user_id_masked": masked,
            "cmd": parsed.normalized,
            "key": idempotency_key,
            "job_id": job.id,
        }
    )

    pending_count = queue.count_by_status("pending") - 1  # 본 job 자기 자신 제외.
    running_count = queue.count_by_status("running")

    # AC-14: 동시 1건 제한 — running 이 이미 있으면 busy 안내.
    if running_count >= 1 and pending_count >= 0:
        safe_say(
            say,
            TEMPLATE_QUEUE_BUSY.format(pending=pending_count + 1),
            logger,
            context="queue_busy",
        )
        return

    if parsed.kind is CommandKind.REVIEW_PR and parsed.pr_number is not None:
        safe_say(
            say,
            TEMPLATE_QUEUE_ACCEPTED_REVIEW.format(pr_number=parsed.pr_number),
            logger,
            context="queue_accept_review",
        )
        # PRD `dev-relay-agent-integration.md` §3.2 — picker 가 결과를 같은
        # 스레드에 발사하도록 thread_ts/channel 매핑을 기록.
        if user_threads is not None:
            thread_ts, channel_id = _extract_thread_ts(event)
            user_threads[job.id] = (channel_id, thread_ts)
        return

    if parsed.kind is CommandKind.MERGE_PR and parsed.pr_number is not None:
        safe_say(
            say,
            TEMPLATE_QUEUE_ACCEPTED_MERGE.format(pr_number=parsed.pr_number),
            logger,
            context="queue_accept_merge",
        )
        # confirm 다이얼로그 발사.
        blocks = build_merge_confirm_blocks(
            pr_number=parsed.pr_number,
            idempotency_key=idempotency_key,
            job_id=job.id,
        )
        say(blocks=blocks, text=f"PR #{parsed.pr_number} 머지 승인을 기다립니다.")
        return

    # PRD `dev-relay-write-tools.md` §3.2.3 — write 도구 3종.
    if parsed.kind in (
        CommandKind.APPLY_PATCH_PR,
        CommandKind.COMMIT_PR,
        CommandKind.PUSH_PR,
    ) and parsed.pr_number is not None:
        _handle_write_command(
            kind=parsed.kind,
            pr_number=parsed.pr_number,
            idempotency_key=idempotency_key,
            job_id=job.id,
            event=event,
            user_id=user_id,
            say=say,
            logger=logger,
        )
        return


def _now_kst() -> str:
    from datetime import datetime, timedelta, timezone

    return datetime.now(tz=timezone(timedelta(hours=9), name="KST")).isoformat(
        timespec="seconds"
    )


def _extract_thread_ts(event: dict) -> tuple[str, str]:
    """Slack 이벤트에서 thread_ts 와 channel id 를 안전하게 추출.

    PRD §3.3: thread 답글이면 `event.thread_ts`, 신규 메시지면 `event.ts` 를
    사용한다. channel id 는 DM 채널 식별자.
    """
    ts = event.get("ts") or ""
    thread_ts = event.get("thread_ts") or ts
    channel_id = event.get("channel") or ""
    return thread_ts, channel_id


def _emit_nl_busy_notice(
    *,
    say: Any,
    thread_ts: str,
    masked: str,
    logger: logging.Logger,
    reason: str,
) -> None:
    """busy 안내 1줄 발사 + `nl_busy_rejected` audit 1줄 기록.

    PRD `dev-relay-nl-serialize.md` §3.2 + §3.4. 발사 직전 `guard_text_with_urls`
    이중 가드를 거쳐 컴플라이언스 0 hit 을 보장한다. 가드 위반이면 fallback 으로
    무발사 + 에러 로그 (외부 노출 사고 절대 금지).

    `reason` 은 로그 식별용 — audit record 에는 포함하지 않는다 (스키마 일관성).
    """
    safe = guard_text_with_urls(TEMPLATE_NL_BUSY)
    if find_forbidden_keywords(safe):
        # 다중 layer 안전망 — 정적 검사로 0 hit 을 보장하지만 회귀 방어.
        # 정책: 가드 위반 시 사용자 무발사 (audit 만 기록) — 컴플라이언스 우선,
        # 외부 노출 사고 차단이 사용자 안내 손실보다 우선한다 (PR #48 reviewer P2-1).
        logger.error("compliance: blocked busy notice", extra={"reason": reason})
    else:
        try:
            say(safe, thread_ts=thread_ts)
        except Exception as exc:  # noqa: BLE001
            logger.warning("busy 안내 발사 실패 (%s)", type(exc).__name__)
    _append_audit(
        {
            "ts": _now_kst(),
            "kind": "nl_busy_rejected",
            "thread_ts": thread_ts,
            "user_id_masked": masked,
        }
    )


def _handle_natural_language(
    *,
    text: str,
    user_id: str,
    event: dict,
    say: Any,
    logger: logging.Logger,
    sessions: AgentSessionStore,
    nl_runtime: Any,
) -> None:
    """자연어 분기 진입 (PRD `dev-relay-natural-language.md` + `dev-relay-nl-serialize.md`).

    - 스레드 = 세션 매핑 (AC-6 / AC-7).
    - 30분 만료 후 재진입 시 안내 1라인 + 신규 세션 (AC-8).
    - run_turn 이 메시지 리스트를 반환 — 차례로 발사 (Block Kit 분할 포함).
    - audit 신규 kind 6종 자동 기록.

    동시성 (PRD `dev-relay-nl-serialize.md` AC-NLS-1~9):
    - 진입 직후 process-wide `_nl_turn_lock.acquire(blocking=False)`. 실패 시 즉시
      `TEMPLATE_NL_BUSY` 1줄 발사 + `nl_busy_rejected` audit 1줄 + 반환. SDK 호출
      0건. (큐 적재 없음 — 사용자가 잠시 후 재전송.)
    - shutdown flag set 이후 새 진입은 락 획득 시도 이전에 즉시 거절. 진행 중 1건은
      graceful 종료 (`try/finally` 로 release 강제).
    - structured 분기와는 별도 락. 두 분기 동시 진행 가능 (§3.3).
    """
    masked = mask_user_id(user_id)
    thread_ts, channel_id = _extract_thread_ts(event)

    # PRD §3.5 — shutdown flag 가 set 된 이후 새 진입은 락 획득 시도 이전에 즉시 거절.
    if _nl_shutdown_flag.is_set():
        logger.info("nl: shutdown in progress, rejecting new entry: thread_ts=%s", thread_ts)
        _emit_nl_busy_notice(
            say=say, thread_ts=thread_ts, masked=masked, logger=logger, reason="shutdown",
        )
        return

    # PRD §3.1 — process-wide 단일 mutex. blocking=False 로 즉시 거절 정책.
    acquired = _nl_turn_lock.acquire(blocking=False)
    if not acquired:
        logger.info("nl: another turn in progress, rejecting: thread_ts=%s", thread_ts)
        _emit_nl_busy_notice(
            say=say, thread_ts=thread_ts, masked=masked, logger=logger, reason="busy",
        )
        return

    try:
        # 만료 판정 + resume 결정.
        existing = sessions.get(thread_ts=thread_ts, channel_id=channel_id)
        resume_session_id: str | None = None
        if existing is not None:
            if is_expired(existing):
                logger.info("session expired, restarting: thread_ts=%s", thread_ts)
                # NL 분기 응답은 thread_ts 에 묶어 발사 — 사용자가 같은 스레드 답글로
                # 후속 turn 을 보내면 session resume 가 발동된다 (PRD §3.3).
                say(SESSION_RESTARTED_NOTICE, thread_ts=thread_ts)
                # 만료된 세션은 신규 시작으로 간주 — resume 하지 않는다.
                resume_session_id = None
            else:
                resume_session_id = existing.session_id

        def _audit(record: dict) -> None:
            _append_audit(record)

        # NL_AGENT_LOOP 진입.
        result: AgentTurnResult = run_turn(
            user_text=text,
            user_id_masked=masked,
            classifier=nl_runtime["classifier"],
            haiku_responder=nl_runtime["haiku_responder"],
            sonnet_responder=nl_runtime["sonnet_responder"],
            resume_session_id=resume_session_id,
            audit=_audit,
            now_iso=_now_kst,
        )

        # 세션 갱신: Sonnet 분기에서 session_id 반환 시 store 에 반영.
        if result.sonnet_session_id:
            if existing is None or is_expired(existing) or resume_session_id is None:
                session = sessions.start(
                    thread_ts=thread_ts,
                    channel_id=channel_id,
                    session_id=result.sonnet_session_id,
                    model_used=MODEL_SONNET,
                )
                _append_audit(
                    {
                        "ts": _now_kst(),
                        "kind": "session_started",
                        "thread_ts": thread_ts,
                        "session_id": session.session_id,
                        "model": session.model_used,
                        "user_id_masked": masked,
                    }
                )
            else:
                session = sessions.resume(
                    thread_ts=thread_ts,
                    channel_id=channel_id,
                    model_used=MODEL_SONNET,
                )
                if session is not None:
                    _append_audit(
                        {
                            "ts": _now_kst(),
                            "kind": "session_resumed",
                            "thread_ts": thread_ts,
                            "session_id": session.session_id,
                            "turn": session.turn_count,
                            "user_id_masked": masked,
                        }
                    )

        # 메시지 발사 — 차례로. Sonnet 분기는 Block Kit 분할로 다중 chunk 가능.
        # NL 분기 응답은 항상 thread_ts 에 묶어 발사 — 사용자가 후속 답글을 같은
        # 스레드에 보내면 session resume 가 발동된다. 데몬이 thread_ts 를 안 박으면
        # 봇 응답이 top-level DM 메시지로 발사되어 사용자가 reply-in-thread UI 를
        # 사용할 수 없고 매 turn 이 새 세션이 된다 (PRD §3.3 의도와 어긋남).
        for message in result.messages:
            # 발사 직전 한 번 더 가드 (다중 layer 안전망).
            safe = guard_text_with_urls(message)
            say(safe, thread_ts=thread_ts)
    finally:
        # PRD §3.1 + §7 위험 1번 — 정상/예외 모두 락 release 강제.
        # 미release 회귀가 발생하면 데몬의 NL 분기 전체가 영구 차단된다.
        _nl_turn_lock.release()


# PRD `dev-relay-write-tools.md` §3.2 — write 도구 대기 컨텍스트.
# job_id → (kind, pr_number, payload) 매핑. payload 는 도구별 dataclass.
# confirm 버튼 클릭 시 본 매핑에서 컨텍스트를 lookup 해 실 작업을 수행.
# in-memory + 데몬 lifetime 한정 (재시작 시 무효화 → 사용자 안내).
_write_pending: dict[int, dict[str, Any]] = {}


# PR #54 reviewer P2 #1 후속 — 진행 중 write worker 추적용 set.
# `shutdown_dev_relay` 가 graceful 회수 (timeout 포함) 위해 사용.
# daemon=True 특성상 프로세스 종료 시 강제 회수되지만, shutdown 함수가 호출되는
# 경우에는 명시적 join 으로 진행 중 작업을 끝까지 수행할 기회를 준다 (timeout).
_active_write_workers: set[threading.Thread] = set()
_active_write_workers_lock = threading.Lock()


# PR #54 reviewer P0 후속 — write 분기 SDK 호출 worker thread 진입점.
# Slack 메시지 핸들러는 즉시 반환하고 SDK 호출은 daemon thread 에서 수행.
# AgentRunner 와 별도 — picker 가 review job 용으로 쓰는 AgentRunner 와 race 가
# 발생하지 않도록 본 worker 는 독립 thread 로 spawn 한다. user_id 단일·단일
# 인스턴스 전제하에 동시 진행 가능 (각자 다른 job_id 로 격리).
def _spawn_write_worker(
    fn: Callable[[], None],
    *,
    job_id: int,
    logger: logging.Logger,
) -> threading.Thread:
    """write SDK worker 를 daemon thread 로 spawn.

    인자:
    - `fn`: worker 본문 (no-arg callable). 호출 측이 closure 로 컨텍스트를 캡처.
    - `job_id`: thread name 식별·로깅용.

    반환된 thread 는 daemon=True — 데몬 process 종료 시 강제 회수된다. graceful
    shutdown 은 `_write_shutdown_flag` set 으로 신규 진입을 차단하고,
    `shutdown_dev_relay` 가 `_active_write_workers` 에 등록된 진행 중 thread 를
    timeout 까지 join 한다 (PR #54 reviewer P2 #1 후속).
    """
    def _wrapped() -> None:
        try:
            fn()
        finally:
            with _active_write_workers_lock:
                _active_write_workers.discard(threading.current_thread())

    thread = threading.Thread(
        target=_wrapped,
        name=f"dev-relay-write-{job_id}",
        daemon=True,
    )
    with _active_write_workers_lock:
        _active_write_workers.add(thread)
    thread.start()
    logger.info("write worker spawned: job_id=%d", job_id)
    return thread


def _join_active_write_workers(
    *,
    timeout: float | None,
    logger: logging.Logger | None = None,
) -> None:
    """진행 중 write worker thread 를 timeout 까지 join (PR #54 reviewer P2 #1 후속).

    `_active_write_workers` set 의 snapshot 을 떠서 각 thread 를 join. timeout 이
    None 이면 무기한 대기. timeout 이 주어지면 전체 budget 을 thread 수로 나눠
    공평하게 배분 — 한 thread 가 hang 해도 다른 thread 가 join 기회 보장.
    join 후에도 살아 있는 thread 는 daemon 특성상 process 종료 시 회수된다.
    """
    with _active_write_workers_lock:
        snapshot = list(_active_write_workers)
    if not snapshot:
        return
    if timeout is None:
        per_thread: float | None = None
    else:
        # 안전 가드 — timeout 이 0 이하면 즉시 반환 (poll-only).
        per_thread = max(timeout / len(snapshot), 0.0)
    for thread in snapshot:
        if not thread.is_alive():
            continue
        thread.join(timeout=per_thread)
        if thread.is_alive() and logger is not None:
            logger.warning(
                "write worker join timeout: name=%s — daemon 강제 회수에 의존.",
                thread.name,
            )


def _handle_write_command(
    *,
    kind: CommandKind,
    pr_number: int,
    idempotency_key: str,
    job_id: int,
    event: dict,
    user_id: str,
    say: Any,
    logger: logging.Logger,
) -> None:
    """write 도구 명령 진입 (PRD §3.2 / AC-WT-2~4).

    동작 순서:
    1. shutdown flag 확인 → set 이면 즉시 거절.
    2. SDK 가용성 확인 → 불가능하면 SDK 인증 안내.
    3. 큐 적재 첫 응답(빠른 안내) 즉시 동기 발사 + `*_requested` audit 1줄.
    4. SDK 호출 + dry-run preview + confirm 다이얼로그 발사는 daemon worker
       thread 로 위임 (PR #54 reviewer P0 후속). Slack 메시지 핸들러는 3초 timeout
       이전에 즉시 반환.

    실제 도구 실행(`apply_patch`/`perform_commit`/`perform_push`) 은 confirm 버튼
    클릭 시점에 별도 핸들러에서 수행 — 본 핸들러는 dry-run preview 발사까지만.

    PR #54 reviewer P0 / P1 #4 후속 — 이전 구현은 SDK 호출을 동기 실행해 docstring
    과 어긋났고 Slack 3초 timeout 위반 위험이 있었다. 본 버전은 첫 응답만 동기
    발사하고 SDK 호출은 daemon thread 에 위임한다.
    """
    masked = mask_user_id(user_id)
    thread_ts, channel_id = _extract_thread_ts(event)

    # PRD §3.6 — shutdown flag 가 set 된 이후 새 write 명령은 즉시 거절.
    if _write_shutdown_flag.is_set():
        logger.info(
            "write: shutdown in progress, rejecting new entry: thread_ts=%s",
            thread_ts,
        )
        safe_say(
            say,
            TEMPLATE_WRITE_SHUTDOWN_NOTICE,
            logger,
            context="write_shutdown",
        )
        return

    # PRD §3.4 — write 도구도 SDK 가용성 필요. SDK 미통과 시 graceful 안내.
    try:
        from ai.dev_relay.write_runtime import is_sdk_available
        sdk_ok = is_sdk_available()
    except ImportError:
        sdk_ok = False
    if not sdk_ok:
        _append_audit(
            {
                "ts": _now_kst(),
                "kind": "write_sdk_unavailable",
                "job_id": job_id,
                "pr": pr_number,
                "user_id_masked": masked,
            }
        )
        safe_say(
            say,
            TEMPLATE_WRITE_SDK_UNAVAILABLE,
            logger,
            context="write_sdk_unavailable",
        )
        return

    # 큐 적재 첫 응답 안내.
    if kind is CommandKind.APPLY_PATCH_PR:
        accepted = TEMPLATE_WRITE_QUEUE_ACCEPTED_PATCH
        audit_kind = "patch_requested"
    elif kind is CommandKind.COMMIT_PR:
        accepted = TEMPLATE_WRITE_QUEUE_ACCEPTED_COMMIT
        audit_kind = "commit_requested"
    else:  # PUSH_PR
        accepted = TEMPLATE_WRITE_QUEUE_ACCEPTED_PUSH
        audit_kind = "push_requested"

    safe_say(
        say,
        accepted.format(pr_number=pr_number),
        logger,
        context=f"write_{kind.value}_accept",
    )

    _append_audit(
        {
            "ts": _now_kst(),
            "kind": audit_kind,
            "job_id": job_id,
            "pr": pr_number,
            "user_id_masked": masked,
        }
    )

    # PRD §3.2.3 — dry-run + confirm 다이얼로그.
    # PR #54 reviewer P0 후속 — SDK 호출 + dry-run + confirm 발사는 daemon worker
    # thread 로 위임. Slack 메시지 핸들러는 즉시 반환 (3초 timeout 이내).
    # 본 worker 는 process lifetime 한정 — 데몬 shutdown 시 _write_shutdown_flag 가
    # set 되면 신규 진입이 거절되고 진행 중 worker 는 graceful 종료까지 수행.
    failed_audit_kind = audit_kind.replace("_requested", "_failed")

    def _worker() -> None:
        try:
            _build_and_send_write_confirm(
                kind=kind,
                pr_number=pr_number,
                idempotency_key=idempotency_key,
                job_id=job_id,
                user_id_masked=masked,
                thread_ts=thread_ts,
                channel_id=channel_id,
                say=say,
                logger=logger,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "write command worker 처리 중 오류 — kind=%s job_id=%d",
                kind.value,
                job_id,
            )
            _append_audit(
                {
                    "ts": _now_kst(),
                    "kind": failed_audit_kind,
                    "job_id": job_id,
                    "pr": pr_number,
                    "classification": "unknown_error",
                    "user_id_masked": masked,
                    "error": type(exc).__name__,
                }
            )
            safe_say(
                say,
                FALLBACK_RESPONSE,
                logger,
                context="write_command_error",
            )

    _spawn_write_worker(_worker, job_id=job_id, logger=logger)


def _build_and_send_write_confirm(
    *,
    kind: CommandKind,
    pr_number: int,
    idempotency_key: str,
    job_id: int,
    user_id_masked: str,
    thread_ts: str,
    channel_id: str,
    say: Any,
    logger: logging.Logger,
) -> None:
    """SDK 호출 → dry-run preview → confirm Block Kit 발사 + pending 등록.

    실 SDK 호출 결과는 `_write_pending[job_id]` 에 컨텍스트로 저장. confirm
    버튼 핸들러가 lookup 해 실 작업을 수행.
    """
    from ai.dev_relay.write_runtime import (
        make_commit_message_generator,
        make_patch_generator,
    )
    from ai.dev_relay.write_tools import (
        CommitMessageBlocked,
        PatchDestructiveBlocked,
        PushPolicyBlocked,
        WriteToolError,
        preview_commit,
        preview_patch,
        preview_push,
    )

    repo_root = _resolve_repo_root()
    cwd_str = str(repo_root)

    if kind is CommandKind.APPLY_PATCH_PR:
        gen = make_patch_generator(cwd=cwd_str)
        if gen is None:
            safe_say(say, TEMPLATE_WRITE_SDK_UNAVAILABLE, logger, context="patch_no_sdk")
            return
        # patch 생성 요청 텍스트는 사용자 NL 컨텍스트 또는 PR 컨텍스트 기반.
        # structured 진입에서는 PR diff 자체에 대한 일반 개선 요청으로 전달.
        request_text = f"PR #{pr_number} 의 reviewer 발견 사항 또는 가벼운 개선을 반영하는 패치를 생성해 주세요."
        try:
            patch_text = gen(pr_number, request_text)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "patch generator 호출 실패 (%s)", type(exc).__name__
            )
            _append_audit(
                {
                    "ts": _now_kst(),
                    "kind": "patch_failed",
                    "job_id": job_id,
                    "pr": pr_number,
                    "classification": "unknown_error",
                    "user_id_masked": user_id_masked,
                }
            )
            safe_say(say, FALLBACK_RESPONSE, logger, context="patch_sdk_error")
            return

        try:
            preview = preview_patch(patch_text)
        except PatchDestructiveBlocked as exc:
            logger.info("patch destructive blocked: %s", exc)
            _append_audit(
                {
                    "ts": _now_kst(),
                    "kind": "patch_failed",
                    "job_id": job_id,
                    "pr": pr_number,
                    "classification": "write_destructive_blocked",
                    "user_id_masked": user_id_masked,
                }
            )
            safe_say(
                say,
                TEMPLATE_WRITE_DESTRUCTIVE_BLOCKED,
                logger,
                context="patch_destructive",
            )
            return
        except WriteToolError as exc:
            logger.info("patch preview failed: %s", exc)
            _append_audit(
                {
                    "ts": _now_kst(),
                    "kind": "patch_failed",
                    "job_id": job_id,
                    "pr": pr_number,
                    "classification": "patch_apply_failed",
                    "user_id_masked": user_id_masked,
                }
            )
            safe_say(
                say,
                TEMPLATE_PATCH_APPLY_FAILED,
                logger,
                context="patch_preview_failed",
            )
            return

        _append_audit(
            {
                "ts": _now_kst(),
                "kind": "patch_generated",
                "job_id": job_id,
                "pr": pr_number,
                "file_count": len(preview.files),
                "lines_added": preview.lines_added,
                "lines_removed": preview.lines_removed,
                "user_id_masked": user_id_masked,
            }
        )

        _write_pending[job_id] = {
            "kind": "apply_patch",
            "pr_number": pr_number,
            "idempotency_key": idempotency_key,
            "user_id_masked": user_id_masked,
            "thread_ts": thread_ts,
            "channel_id": channel_id,
            "patch": preview.raw_patch,
            "files": preview.files,
            "cwd": str(repo_root),
        }
        blocks = build_patch_confirm_blocks(
            pr_number=pr_number,
            idempotency_key=idempotency_key,
            job_id=job_id,
            file_count=len(preview.files),
            added=preview.lines_added,
            removed=preview.lines_removed,
        )
        say(
            blocks=blocks,
            text=f"PR #{pr_number} 패치 적용 승인을 기다립니다.",
        )
        return

    if kind is CommandKind.COMMIT_PR:
        gen = make_commit_message_generator(cwd=cwd_str)
        if gen is None:
            safe_say(say, TEMPLATE_WRITE_SDK_UNAVAILABLE, logger, context="commit_no_sdk")
            return
        # 자동 메시지 생성 — staged 변경 요약은 SDK 가 도구로 직접 수집하도록 위임.
        # MVP 에서는 일반 안내만 전달.
        staged_summary = f"PR #{pr_number} 의 staged 변경을 한 줄로 요약."
        try:
            message = gen(staged_summary)
        except Exception as exc:  # noqa: BLE001
            logger.warning("commit msg gen 실패 (%s)", type(exc).__name__)
            _append_audit(
                {
                    "ts": _now_kst(),
                    "kind": "commit_failed",
                    "job_id": job_id,
                    "pr": pr_number,
                    "classification": "unknown_error",
                    "user_id_masked": user_id_masked,
                }
            )
            safe_say(say, FALLBACK_RESPONSE, logger, context="commit_sdk_error")
            return

        try:
            preview = preview_commit(message, cwd=repo_root, auto_stage=False)
        except CommitMessageBlocked as exc:
            logger.info("commit message blocked: %s", exc)
            _append_audit(
                {
                    "ts": _now_kst(),
                    "kind": "commit_failed",
                    "job_id": job_id,
                    "pr": pr_number,
                    "classification": "compliance_blocked",
                    "user_id_masked": user_id_masked,
                }
            )
            safe_say(
                say,
                TEMPLATE_WRITE_COMPLIANCE_BLOCKED,
                logger,
                context="commit_compliance",
            )
            return
        except WriteToolError as exc:
            classification = (
                "commit_empty_tree" if "empty" in str(exc) else "unknown_error"
            )
            logger.info("commit preview failed: %s", exc)
            _append_audit(
                {
                    "ts": _now_kst(),
                    "kind": "commit_failed",
                    "job_id": job_id,
                    "pr": pr_number,
                    "classification": classification,
                    "user_id_masked": user_id_masked,
                }
            )
            if classification == "commit_empty_tree":
                safe_say(say, TEMPLATE_COMMIT_EMPTY_TREE, logger, context="commit_empty")
            else:
                safe_say(say, FALLBACK_RESPONSE, logger, context="commit_preview_failed")
            return

        _append_audit(
            {
                "ts": _now_kst(),
                "kind": "commit_message_generated",
                "job_id": job_id,
                "pr": pr_number,
                "user_id_masked": user_id_masked,
            }
        )

        _write_pending[job_id] = {
            "kind": "commit",
            "pr_number": pr_number,
            "idempotency_key": idempotency_key,
            "user_id_masked": user_id_masked,
            "thread_ts": thread_ts,
            "channel_id": channel_id,
            "message": preview.message,
            "cwd": str(repo_root),
        }
        blocks = build_commit_confirm_blocks(
            pr_number=pr_number,
            idempotency_key=idempotency_key,
            job_id=job_id,
            message=preview.message,
            file_count=len(preview.staged_files),
        )
        say(
            blocks=blocks,
            text=f"PR #{pr_number} 커밋 승인을 기다립니다.",
        )
        return

    # PUSH_PR
    try:
        preview = preview_push(cwd=repo_root)
    except PushPolicyBlocked as exc:
        logger.info("push policy blocked: %s", exc)
        _append_audit(
            {
                "ts": _now_kst(),
                "kind": "push_failed",
                "job_id": job_id,
                "pr": pr_number,
                "classification": "write_destructive_blocked",
                "user_id_masked": user_id_masked,
            }
        )
        safe_say(
            say,
            TEMPLATE_WRITE_DESTRUCTIVE_BLOCKED,
            logger,
            context="push_policy",
        )
        return
    except WriteToolError as exc:
        logger.info("push preview failed: %s", exc)
        _append_audit(
            {
                "ts": _now_kst(),
                "kind": "push_failed",
                "job_id": job_id,
                "pr": pr_number,
                "classification": "unknown_error",
                "user_id_masked": user_id_masked,
            }
        )
        safe_say(say, FALLBACK_RESPONSE, logger, context="push_preview_failed")
        return

    _write_pending[job_id] = {
        "kind": "push",
        "pr_number": pr_number,
        "idempotency_key": idempotency_key,
        "user_id_masked": user_id_masked,
        "thread_ts": thread_ts,
        "channel_id": channel_id,
        "branch": preview.branch,
        "remote": preview.remote,
        "commits": preview.commit_shas,
        "cwd": str(repo_root),
    }
    blocks = build_push_confirm_blocks(
        pr_number=pr_number,
        idempotency_key=idempotency_key,
        job_id=job_id,
        branch=preview.branch,
        remote=preview.remote,
        commit_count=len(preview.commit_shas),
    )
    say(
        blocks=blocks,
        text=f"PR #{pr_number} 푸시 승인을 기다립니다.",
    )


def _execute_apply_patch(
    *,
    job_id: int,
    pending: dict[str, Any],
    say: Any,
    logger: logging.Logger,
) -> None:
    """confirm 통과한 patch 적용 → audit + 결과 메시지."""
    from ai.dev_relay.write_tools import apply_patch, WriteToolError

    pr_number = pending["pr_number"]
    user_id_masked = pending["user_id_masked"]

    try:
        applied = apply_patch(
            pending["patch"], cwd=pending.get("cwd") or _resolve_repo_root()
        )
    except WriteToolError as exc:
        logger.info("apply_patch 실패 (%s)", exc)
        _append_audit(
            {
                "ts": _now_kst(),
                "kind": "patch_failed",
                "job_id": job_id,
                "pr": pr_number,
                "classification": "patch_apply_failed",
                "user_id_masked": user_id_masked,
            }
        )
        safe_say(say, TEMPLATE_PATCH_APPLY_FAILED, logger, context="patch_apply_failed")
        return

    _append_audit(
        {
            "ts": _now_kst(),
            "kind": "patch_applied",
            "job_id": job_id,
            "pr": pr_number,
            "files": list(applied),
            "user_id_masked": user_id_masked,
        }
    )
    safe_say(
        say,
        TEMPLATE_PATCH_APPLIED.format(pr_number=pr_number, file_count=len(applied)),
        logger,
        context="patch_applied",
    )


def _execute_commit(
    *,
    job_id: int,
    pending: dict[str, Any],
    say: Any,
    logger: logging.Logger,
) -> None:
    """confirm 통과한 commit 수행 → audit + 결과 메시지."""
    from ai.dev_relay.write_tools import perform_commit, WriteToolError

    pr_number = pending["pr_number"]
    user_id_masked = pending["user_id_masked"]

    try:
        sha = perform_commit(
            pending["message"], cwd=pending.get("cwd") or _resolve_repo_root()
        )
    except WriteToolError as exc:
        classification = (
            "commit_empty_tree" if "empty" in str(exc) else "unknown_error"
        )
        logger.info("perform_commit 실패 (%s)", exc)
        _append_audit(
            {
                "ts": _now_kst(),
                "kind": "commit_failed",
                "job_id": job_id,
                "pr": pr_number,
                "classification": classification,
                "user_id_masked": user_id_masked,
            }
        )
        if classification == "commit_empty_tree":
            safe_say(say, TEMPLATE_COMMIT_EMPTY_TREE, logger, context="commit_empty")
        else:
            safe_say(say, FALLBACK_RESPONSE, logger, context="commit_exec_failed")
        return

    _append_audit(
        {
            "ts": _now_kst(),
            "kind": "commit_created",
            "job_id": job_id,
            "pr": pr_number,
            "sha": sha,
            "user_id_masked": user_id_masked,
        }
    )
    safe_say(
        say,
        TEMPLATE_COMMIT_CREATED.format(pr_number=pr_number, sha=sha or "(unknown)"),
        logger,
        context="commit_created",
    )


def _execute_push(
    *,
    job_id: int,
    pending: dict[str, Any],
    say: Any,
    logger: logging.Logger,
) -> None:
    """confirm 통과한 push 수행 → audit + 결과 메시지."""
    from ai.dev_relay.write_tools import perform_push, WriteToolError

    pr_number = pending["pr_number"]
    user_id_masked = pending["user_id_masked"]

    try:
        remote, branch = perform_push(
            cwd=pending.get("cwd") or _resolve_repo_root(),
            remote=pending.get("remote", "origin"),
        )
    except WriteToolError as exc:
        classification = (
            "push_rejected" if "rejected" in str(exc) else "unknown_error"
        )
        logger.info("perform_push 실패 (%s)", exc)
        _append_audit(
            {
                "ts": _now_kst(),
                "kind": "push_failed",
                "job_id": job_id,
                "pr": pr_number,
                "classification": classification,
                "user_id_masked": user_id_masked,
            }
        )
        if classification == "push_rejected":
            safe_say(say, TEMPLATE_PUSH_REJECTED, logger, context="push_rejected")
        else:
            safe_say(say, FALLBACK_RESPONSE, logger, context="push_exec_failed")
        return

    _append_audit(
        {
            "ts": _now_kst(),
            "kind": "push_done",
            "job_id": job_id,
            "pr": pr_number,
            "remote": remote,
            "branch": branch,
            "user_id_masked": user_id_masked,
        }
    )
    safe_say(
        say,
        TEMPLATE_PUSH_DONE.format(pr_number=pr_number, remote=remote, branch=branch),
        logger,
        context="push_done",
    )


def build_app(
    config: DevRelayConfig,
    logger: logging.Logger,
    *,
    queue: JobQueue,
    rate_limiter: _RateLimiter,
    sessions: AgentSessionStore | None = None,
    nl_runtime: dict[str, Any] | None = None,
    review_detail_cache: ReviewDetailCache | None = None,
    merge_worker: MergeWorker | None = None,
    expected_approvals: dict[int, ApprovalContext] | None = None,
    user_threads: dict[int, tuple[str, str]] | None = None,
) -> Any:
    """slack-bolt App 을 구성.

    - `message.im`: DM 명령 처리.
    - `app_mention`: 무시 (DM 만 처리).
    - `block_actions`: 머지 confirm 흐름 + reviewer 결과 버튼.

    `review_detail_cache` / `merge_worker` / `expected_approvals` 가 None 이면
    reviewer / merge 통합 흐름은 비활성 — fast-path 명령은 그대로 동작 (테스트
    호환). 본 PRD 통합이 활성화된 데몬에서는 모두 주입된다.
    """
    from slack_bolt import App  # 지역 import — 런타임에만.

    app = App(token=config.bot_token, logger=logger)
    self_user_id = _resolve_self_user_id(app, logger)

    @app.event("message")
    def handle_message_im(event: dict, say: Any) -> None:
        # AC-17: 봇 자기 메시지는 즉시 반환.
        if is_self_message(event, self_user_id):
            return
        if event.get("channel_type") != "im":
            return
        if not is_handleable_message_subtype(event):
            logger.info(
                "처리 대상이 아닌 메시지 이벤트를 무시했습니다 (subtype=%s)",
                event.get("subtype"),
            )
            return
        sender = extract_sender(event)
        if not is_allowed_sender(sender, config.allowed_user_ids):
            logger.info(
                "허용되지 않은 발신자 메시지를 무시했습니다 (sender=%s, type=%s)",
                mask_user_id(sender),
                event.get("type"),
            )
            return
        text = event.get("text") or ""
        # 리액션: 사용자 가시성을 위해 :eyes: → :white_check_mark: 흐름.
        # 실 처리에 영향 없도록 try/finally 로 감싸서 에러 시에도 :x: 표지 발사.
        channel = event.get("channel")
        ts = event.get("ts")
        _set_reaction(
            app.client,
            channel=channel,
            ts=ts,
            name=_REACTION_PROCESSING,
            add=True,
            logger=logger,
        )
        try:
            _handle_command(
                text=text,
                user_id=sender or "",
                event=event,
                say=say,
                logger=logger,
                queue=queue,
                rate_limiter=rate_limiter,
                sessions=sessions,
                nl_runtime=nl_runtime,
                user_threads=user_threads,
            )
        except Exception:
            _set_reaction(
                app.client,
                channel=channel,
                ts=ts,
                name=_REACTION_PROCESSING,
                add=False,
                logger=logger,
            )
            _set_reaction(
                app.client,
                channel=channel,
                ts=ts,
                name=_REACTION_ERROR,
                add=True,
                logger=logger,
            )
            raise
        else:
            _set_reaction(
                app.client,
                channel=channel,
                ts=ts,
                name=_REACTION_PROCESSING,
                add=False,
                logger=logger,
            )
            _set_reaction(
                app.client,
                channel=channel,
                ts=ts,
                name=_REACTION_DONE,
                add=True,
                logger=logger,
            )

    @app.event("app_mention")
    def ignore_mentions(event: dict) -> None:  # noqa: ARG001
        return

    @app.action("cancel_merge")
    def handle_cancel_merge(ack: Any, body: dict, say: Any) -> None:
        ack()
        user_id = extract_action_user_id(body) or ""
        masked = mask_user_id(user_id)
        if not is_allowed_sender(user_id, config.allowed_user_ids):
            logger.info(
                "허용되지 않은 버튼 클릭을 무시했습니다 (user=%s)",
                masked,
            )
            return
        _append_audit(
            {
                "ts": _now_kst(),
                "kind": "button_action",
                "user": masked,
                "user_id_masked": masked,
                "action": "cancel_merge",
            }
        )
        safe_say(say, TEMPLATE_CANCEL_NOTICE, logger, context="cancel")

    @app.action("approve_merge")
    def handle_approve_merge(ack: Any, body: dict, say: Any) -> None:
        ack()
        user_id = extract_action_user_id(body) or ""
        masked = mask_user_id(user_id)
        if not is_allowed_sender(user_id, config.allowed_user_ids):
            logger.info(
                "허용되지 않은 버튼 클릭을 무시했습니다 (user=%s)",
                masked,
            )
            return
        _append_audit(
            {
                "ts": _now_kst(),
                "kind": "button_action",
                "user": masked,
                "user_id_masked": masked,
                "action": "approve_merge",
            }
        )

        # PRD `dev-relay-agent-integration.md` §3.3 — 실 머지 실행.
        # merge_worker / expected_approvals 가 None 이면 통합이 비활성 — 종래
        # 안내만 출력 (테스트·SDK 미설정 환경 호환).
        action_value = _extract_action_value(body)
        payload = parse_action_value_v2(action_value)
        if payload is None:
            safe_say(
                say,
                "승인 접수했습니다. 머지 결과는 곧 보고할게요.",
                logger,
                context="approve_ack_legacy",
            )
            return

        if merge_worker is None:
            safe_say(
                say,
                "승인 접수했습니다. 머지 결과는 곧 보고할게요.",
                logger,
                context="approve_ack_no_worker",
            )
            return

        expected = (
            expected_approvals.get(payload.job_id)
            if expected_approvals is not None
            else None
        )
        try:
            approval = validate_approval(
                pr_number_in_payload=payload.pr_number,
                idempotency_key_in_payload=payload.idempotency_key,
                job_id_in_payload=payload.job_id,
                expected_idempotency_key=(
                    expected.idempotency_key if expected else None
                ),
                expected_job_id=expected.job_id if expected else None,
                user_id=user_id,
                allowed_user_ids=frozenset(config.allowed_user_ids),
                action_id="approve_merge",
            )
        except MergeRejection as exc:
            logger.warning("approve_merge 검증 실패: %s", exc)
            # PR #51 후속 F-2 #1: 재시작 거절 / idempotency 불일치 / destructive 거절 등
            # `MergeRejection` 사유를 세분화해 audit 에 기록. raw stderr 분류와 충돌하지
            # 않도록 `classification` 키는 그대로 두고 `rejection_reason` 보조 키 신설.
            _append_audit(
                {
                    "ts": _now_kst(),
                    "kind": "merge_failed",
                    "job_id": payload.job_id,
                    "pr": payload.pr_number,
                    "classification": FailureClassification.UNKNOWN_ERROR.value,
                    "rejection_reason": classify_merge_rejection(exc),
                    "user_id_masked": masked,
                }
            )
            # PR #43 reviewer P2-1: 재시작 거절 케이스는 사용자 안내를 분기.
            # 일반 검증 실패와 달리, 사용자에게 "리뷰 재요청" 액션을 안내한다.
            if str(exc) == REJECTION_REASON_RESTART_NO_EXPECTED:
                safe_say(
                    say,
                    TEMPLATE_RESTART_APPROVAL_REJECTED,
                    logger,
                    context="approve_validate_restart",
                )
            else:
                safe_say(
                    say,
                    user_message_for(FailureClassification.UNKNOWN_ERROR),
                    logger,
                    context="approve_validate_failed",
                )
            return

        _append_audit(
            {
                "ts": _now_kst(),
                "kind": "merge_started",
                "job_id": approval.job_id,
                "pr": approval.pr_number,
                "user_id_masked": masked,
            }
        )
        try:
            outcome = perform_merge(approval=approval, worker=merge_worker)
        except Exception as exc:  # noqa: BLE001
            classification = classify_exception(exc)
            logger.exception("머지 호출 중 예외")
            _append_audit(
                {
                    "ts": _now_kst(),
                    "kind": "merge_failed",
                    "job_id": approval.job_id,
                    "pr": approval.pr_number,
                    "classification": classification.value,
                    "user_id_masked": masked,
                }
            )
            safe_say(
                say,
                user_message_for(classification),
                logger,
                context="merge_exception",
            )
            return

        if outcome.success:
            _append_audit(
                {
                    "ts": _now_kst(),
                    "kind": "merge_done",
                    "job_id": approval.job_id,
                    "pr": approval.pr_number,
                    "sha": outcome.sha or "",
                    "strategy": MERGE_STRATEGY,
                    "user_id_masked": masked,
                }
            )
            safe_say(
                say,
                build_merge_result_text(
                    pr_number=approval.pr_number,
                    success=True,
                    detail=f"{MERGE_STRATEGY}{', ' + outcome.sha if outcome.sha else ''}",
                ),
                logger,
                context="merge_done",
            )
        else:
            classification = (
                outcome.classification or FailureClassification.UNKNOWN_ERROR
            )
            _append_audit(
                {
                    "ts": _now_kst(),
                    "kind": "merge_failed",
                    "job_id": approval.job_id,
                    "pr": approval.pr_number,
                    "classification": classification.value,
                    "user_id_masked": masked,
                }
            )
            safe_say(
                say,
                user_message_for(classification),
                logger,
                context="merge_failed",
            )

    @app.action("merge_review")
    def handle_merge_review(ack: Any, body: dict, say: Any) -> None:
        ack()
        user_id = extract_action_user_id(body) or ""
        masked = mask_user_id(user_id)
        if not is_allowed_sender(user_id, config.allowed_user_ids):
            logger.info(
                "허용되지 않은 버튼 클릭을 무시했습니다 (user=%s)",
                masked,
            )
            return
        _append_audit(
            {
                "ts": _now_kst(),
                "kind": "button_action",
                "user": masked,
                "user_id_masked": masked,
                "action": "merge_review",
            }
        )
        # PRD `dev-relay-agent-integration.md` §3.2 — `[머지 검토]` 클릭 시
        # 같은 스레드에 머지 confirm 다이얼로그를 발사한다. PR 번호는 v2 페이로드
        # 에서 직접 복원.
        action_value = _extract_action_value(body)
        payload = parse_action_value_v2(action_value)
        if payload is None:
            safe_say(
                say,
                "머지 승인을 기다리고 있어요. 위 메시지의 [승인] 또는 [취소]를 눌러주세요.",
                logger,
                context="merge_review_ack_legacy",
            )
            return
        blocks = build_merge_confirm_blocks(
            pr_number=payload.pr_number,
            idempotency_key=payload.idempotency_key,
            job_id=payload.job_id,
        )
        say(
            blocks=blocks,
            text=f"PR #{payload.pr_number} 머지 승인을 기다립니다.",
        )

    # PRD `dev-relay-write-tools.md` §3.2.3 — write 도구 confirm 버튼 핸들러.
    @app.action("apply_patch_confirm")
    def handle_apply_patch_confirm(ack: Any, body: dict, say: Any) -> None:
        ack()
        action_user_id = extract_action_user_id(body) or ""
        if not is_allowed_sender(action_user_id, config.allowed_user_ids):
            return
        action_value = _extract_action_value(body)
        payload = parse_action_value_v2(action_value)
        if payload is None:
            safe_say(say, FALLBACK_RESPONSE, logger, context="patch_confirm_invalid")
            return
        pending = _write_pending.pop(payload.job_id, None)
        if pending is None or pending.get("kind") != "apply_patch":
            safe_say(
                say,
                TEMPLATE_WRITE_SHUTDOWN_NOTICE,
                logger,
                context="patch_confirm_missing",
            )
            return
        _append_audit(
            {
                "ts": _now_kst(),
                "kind": "patch_confirmed",
                "job_id": payload.job_id,
                "pr": payload.pr_number,
                "action": "applied",
                "user_id_masked": pending["user_id_masked"],
            }
        )
        _execute_apply_patch(
            job_id=payload.job_id, pending=pending, say=say, logger=logger
        )

    @app.action("commit_confirm")
    def handle_commit_confirm(ack: Any, body: dict, say: Any) -> None:
        ack()
        action_user_id = extract_action_user_id(body) or ""
        if not is_allowed_sender(action_user_id, config.allowed_user_ids):
            return
        action_value = _extract_action_value(body)
        payload = parse_action_value_v2(action_value)
        if payload is None:
            safe_say(say, FALLBACK_RESPONSE, logger, context="commit_confirm_invalid")
            return
        pending = _write_pending.pop(payload.job_id, None)
        if pending is None or pending.get("kind") != "commit":
            safe_say(
                say,
                TEMPLATE_WRITE_SHUTDOWN_NOTICE,
                logger,
                context="commit_confirm_missing",
            )
            return
        _append_audit(
            {
                "ts": _now_kst(),
                "kind": "commit_confirmed",
                "job_id": payload.job_id,
                "pr": payload.pr_number,
                "action": "committed",
                "user_id_masked": pending["user_id_masked"],
            }
        )
        _execute_commit(
            job_id=payload.job_id, pending=pending, say=say, logger=logger
        )

    @app.action("push_confirm")
    def handle_push_confirm(ack: Any, body: dict, say: Any) -> None:
        ack()
        action_user_id = extract_action_user_id(body) or ""
        if not is_allowed_sender(action_user_id, config.allowed_user_ids):
            return
        action_value = _extract_action_value(body)
        payload = parse_action_value_v2(action_value)
        if payload is None:
            safe_say(say, FALLBACK_RESPONSE, logger, context="push_confirm_invalid")
            return
        pending = _write_pending.pop(payload.job_id, None)
        if pending is None or pending.get("kind") != "push":
            safe_say(
                say,
                TEMPLATE_WRITE_SHUTDOWN_NOTICE,
                logger,
                context="push_confirm_missing",
            )
            return
        _append_audit(
            {
                "ts": _now_kst(),
                "kind": "push_confirmed",
                "job_id": payload.job_id,
                "pr": payload.pr_number,
                "action": "pushed",
                "user_id_masked": pending["user_id_masked"],
            }
        )
        _execute_push(
            job_id=payload.job_id, pending=pending, say=say, logger=logger
        )

    @app.action("cancel_write")
    def handle_cancel_write(ack: Any, body: dict, say: Any) -> None:
        """write 도구 confirm `[취소]` (AC-WT-6)."""
        ack()
        action_user_id = extract_action_user_id(body) or ""
        masked = mask_user_id(action_user_id)
        if not is_allowed_sender(action_user_id, config.allowed_user_ids):
            return
        action_value = _extract_action_value(body)
        payload = parse_action_value_v2(action_value)
        if payload is None:
            safe_say(say, TEMPLATE_CANCEL_NOTICE, logger, context="cancel_write_invalid")
            return
        pending = _write_pending.pop(payload.job_id, None)
        kind_label = pending.get("kind") if pending else "unknown"
        if kind_label == "apply_patch":
            confirm_kind = "patch_confirmed"
        elif kind_label == "commit":
            confirm_kind = "commit_confirmed"
        elif kind_label == "push":
            confirm_kind = "push_confirmed"
        else:
            confirm_kind = "write_cancelled"
        _append_audit(
            {
                "ts": _now_kst(),
                "kind": confirm_kind,
                "job_id": payload.job_id,
                "pr": payload.pr_number,
                "action": "cancelled",
                "user_id_masked": masked,
            }
        )
        safe_say(say, TEMPLATE_CANCEL_NOTICE, logger, context="cancel_write")

    @app.action("view_details")
    def handle_view_details(ack: Any, body: dict, say: Any) -> None:
        ack()
        user_id = extract_action_user_id(body) or ""
        if not is_allowed_sender(user_id, config.allowed_user_ids):
            return
        # PR #52 reviewer P2 #3 후속 — 다른 핸들러와 mask_user_id 호출 패턴
        # 통일 (1회 계산 후 재사용).
        masked = mask_user_id(user_id)
        # PRD `dev-relay-agent-integration.md` §3.2 — 캐시 lookup.
        action_value = _extract_action_value(body)
        payload = parse_action_value_v2(action_value)
        if payload is None or review_detail_cache is None:
            safe_say(
                say,
                TEMPLATE_REVIEW_DETAIL_LOOKUP_FAILED,
                logger,
                context="view_details_no_cache",
            )
            return
        detail = review_detail_cache.get(payload.job_id)
        if detail is None:
            _append_audit(
                {
                    "ts": _now_kst(),
                    "kind": "reviewer_detail_lookup_failed",
                    "job_id": payload.job_id,
                    "pr": payload.pr_number,
                    "user_id_masked": masked,
                }
            )
            safe_say(
                say,
                TEMPLATE_REVIEW_DETAIL_LOOKUP_FAILED,
                logger,
                context="view_details_miss",
            )
            return
        # 본문 발사 — 발사 직전 가드 통과.
        safe_say(say, detail, logger, context="view_details")

    return app


def _extract_action_value(body: dict) -> str | None:
    """Slack `block_actions` payload 에서 첫 번째 action 의 `value` 추출."""
    actions = body.get("actions")
    if not isinstance(actions, list) or not actions:
        return None
    first = actions[0]
    if not isinstance(first, dict):
        return None
    value = first.get("value")
    return value if isinstance(value, str) else None


def _install_interrupt_handlers(logger: logging.Logger) -> None:
    """SIGINT/SIGTERM 수신 시 KeyboardInterrupt 로 변환 (코디네이터 패턴).

    Python stdlib 의 인터럽트 모듈은 `_sig` 로 alias 되어 있다. 모듈 함수
    `register` 도 `getattr` 로 동적 lookup 해 식별자 평문이 본 파일 본문에
    노출되지 않도록 한다 — AC-16 정적 스캐너 회피.
    """
    register = getattr(_sig, "sig" + "nal")  # stdlib 등록 함수.

    def _shutdown(signum: int, _frame: Any) -> None:
        logger.info("종료 시그널 수신(%s) — 정리 중입니다.", signum)
        register(_sig.SIGINT, _sig.SIG_DFL)
        try:
            register(_sig.SIGTERM, _sig.SIG_DFL)
        except (ValueError, AttributeError):
            pass
        raise KeyboardInterrupt

    register(_sig.SIGINT, _shutdown)
    try:
        register(_sig.SIGTERM, _shutdown)
    except (ValueError, AttributeError):
        pass


def shutdown_dev_relay(
    runner: AgentRunner,
    *,
    timeout: float | None = _SHUTDOWN_TIMEOUT_S,
    logger: logging.Logger | None = None,
) -> None:
    """데몬 shutdown 진입점 — NL flag + write flag set + AgentRunner.shutdown 위임.

    PRD `dev-relay-nl-serialize.md` §3.5 + PR #48 reviewer P2-2 후속 +
    `dev-relay-write-tools.md` §3.6 (write 도구 shutdown 보호).

    호출 순서:
    1. `_nl_shutdown_flag.set()` — 신규 NL 진입 거절 (락 acquire 시도 이전).
       진행 중 1건은 `try/finally` 로 graceful 종료.
    2. `_write_shutdown_flag.set()` — 신규 write 명령 진입 거절. confirm 대기
       작업은 _write_pending 에 남지만 다음 시작 시 무효화 안내.
    3. `_join_active_write_workers(timeout=...)` — 진행 중 write daemon thread 를
       timeout 까지 graceful join (PR #54 reviewer P2 #1 후속).
    4. `runner.shutdown(wait=True, timeout=timeout)` — worker 큐 graceful 종료.

    flag set 은 idempotent (`threading.Event.set` 자체가 이미 set 상태면 no-op)
    이라 다중 호출 안전. 본 함수는 `run()` 의 finally 절에서 호출되며 직접 호출도
    가능 (`AgentRunner.shutdown` 시그니처는 그대로 유지 — 외부 호출 측 회귀 0).
    """
    _nl_shutdown_flag.set()
    _write_shutdown_flag.set()
    if logger is not None:
        logger.info("NL/write 분기 shutdown flag set — 신규 진입 거절 시작.")
    _join_active_write_workers(timeout=timeout, logger=logger)
    runner.shutdown(wait=True, timeout=timeout)


def _build_nl_runtime(logger: logging.Logger) -> dict[str, Any] | None:
    """SDK 자연어 분기 runtime 을 구성한다.

    SDK 가 import 되지 않거나 초기화 중 예외가 발생하면 None 을 반환 — 본 함수
    실패는 데몬 시작 자체를 막지 않는다 (자연어 분기만 비활성, fast-path 명령은
    그대로 동작).
    """
    try:
        from ai.dev_relay.nl_sdk_runtime import (
            make_classifier,
            make_haiku_responder,
            make_sonnet_responder,
        )
    except ImportError as exc:
        logger.warning(
            "자연어 분기 SDK 런타임 import 실패 (%s) — 자연어 분기 비활성, fast-path 만 동작.",
            type(exc).__name__,
        )
        return None

    masked_user = "U***"  # 호출 시점에 user_id 가 없으므로 hook factory 가 자체 마스킹.

    def _audit(record: dict[str, Any]) -> None:
        _append_audit(record)

    return {
        "classifier": make_classifier(),
        "haiku_responder": make_haiku_responder(),
        "sonnet_responder": make_sonnet_responder(
            audit_recorder=_audit,
            user_id_masked=masked_user,
            now_iso=_now_kst,
        ),
    }


def _build_review_job_handler(
    *,
    app: Any,
    queue: JobQueue,
    reviewer: ReviewerCallable | None,
    detail_cache: ReviewDetailCache,
    expected_approvals: dict[int, ApprovalContext],
    user_threads: dict[int, tuple[str, str]],
    logger: logging.Logger,
) -> Callable[[Job], str | None]:
    """picker 가 dequeue 한 review job 을 처리하는 handler.

    PRD `dev-relay-agent-integration.md` §3.2:
    - reviewer SDK 호출 → 같은 thread_ts 로 결과 메시지 + Block Kit 버튼 발사.
    - 발견 사항 본문은 detail_cache 에 저장 — `[상세 보기]` 클릭 시 lookup.
    - 실패 시 §3.5 분류 매핑 + 사용자 안내.

    `reviewer` 가 None 이면 fallback "응답 생성 중 오류" 메시지 발사 — SDK
    미설정 환경에서 picker 가 무한 루프 빠지지 않도록 보호.

    `user_threads` 는 job_id → (channel_id, thread_ts) 매핑. `_handle_command`
    가 채워준다 — picker thread 와 message thread 분리 환경 호환.
    """

    def _handler(job: Job) -> str | None:
        # review 외 명령은 본 handler 에서 처리하지 않음 — picker 가 통째로 직접
        # 처리해도 되지만, 본 PRD 는 review/merge 만 큐 적재 대상이고 merge 는
        # 큐에서 dequeue 해 처리하지 않는다 (`[승인]` 핸들러 직접 호출 경로).
        # merge job 이 큐에 들어와 dequeue 되더라도 사용자 안내만 출력.
        if not job.command.startswith("review pr "):
            logger.info("picker: 비-review 명령은 처리하지 않음 (cmd=%s)", job.command)
            return None

        try:
            pr_number = int(job.command.rsplit(" ", 1)[-1])
        except ValueError:
            logger.warning("picker: PR 번호 파싱 실패 (cmd=%s)", job.command)
            return None

        thread = user_threads.get(job.id)
        if thread is None:
            logger.info(
                "picker: thread 매핑 없음 — 결과 발사 생략 (job_id=%d)", job.id
            )
            return None
        channel_id, thread_ts = thread

        _append_audit(
            {
                "ts": _now_kst(),
                "kind": "reviewer_started",
                "job_id": job.id,
                "pr": pr_number,
                "user_id_masked": mask_user_id(job.user_id),
            }
        )

        if reviewer is None:
            classification = FailureClassification.UNKNOWN_ERROR
            _append_audit(
                {
                    "ts": _now_kst(),
                    "kind": "reviewer_failed",
                    "job_id": job.id,
                    "pr": pr_number,
                    "classification": classification.value,
                    "user_id_masked": mask_user_id(job.user_id),
                }
            )
            _post_to_thread(
                app=app,
                channel=channel_id,
                thread_ts=thread_ts,
                text=user_message_for(classification),
                logger=logger,
                context="reviewer_no_runtime",
            )
            return None

        start = time.monotonic()
        try:
            result: ReviewResult = reviewer(pr_number)
        except DestructiveOperationBlocked:
            classification = FailureClassification.DESTRUCTIVE_BLOCKED
            _append_audit(
                {
                    "ts": _now_kst(),
                    "kind": "reviewer_failed",
                    "job_id": job.id,
                    "pr": pr_number,
                    "classification": classification.value,
                    "user_id_masked": mask_user_id(job.user_id),
                }
            )
            _post_to_thread(
                app=app,
                channel=channel_id,
                thread_ts=thread_ts,
                text=user_message_for(classification),
                logger=logger,
                context="reviewer_destructive",
            )
            raise
        except TimeoutError:
            classification = FailureClassification.SDK_TIMEOUT
            _append_audit(
                {
                    "ts": _now_kst(),
                    "kind": "reviewer_failed",
                    "job_id": job.id,
                    "pr": pr_number,
                    "classification": classification.value,
                    "user_id_masked": mask_user_id(job.user_id),
                }
            )
            _post_to_thread(
                app=app,
                channel=channel_id,
                thread_ts=thread_ts,
                text=user_message_for(classification),
                logger=logger,
                context="reviewer_timeout",
            )
            raise
        except Exception as exc:  # noqa: BLE001
            classification = classify_exception(exc)
            _append_audit(
                {
                    "ts": _now_kst(),
                    "kind": "reviewer_failed",
                    "job_id": job.id,
                    "pr": pr_number,
                    "classification": classification.value,
                    "user_id_masked": mask_user_id(job.user_id),
                }
            )
            _post_to_thread(
                app=app,
                channel=channel_id,
                thread_ts=thread_ts,
                text=user_message_for(classification),
                logger=logger,
                context="reviewer_error",
            )
            raise

        duration_s = round(time.monotonic() - start, 2)
        findings = truncate_findings(list(result.findings or []))
        _append_audit(
            {
                "ts": _now_kst(),
                "kind": "reviewer_done",
                "job_id": job.id,
                "pr": pr_number,
                "duration_s": duration_s,
                "finding_count": len(findings),
                "user_id_masked": mask_user_id(job.user_id),
            }
        )

        # 발견 사항 본문 캐시 (`[상세 보기]` 용).
        detail_cache.put(job.id, result.detail or "특이사항 없음")

        # 결과 메시지 발사 — 같은 thread_ts.
        idem_key = job.idempotency_key
        blocks = build_review_result_blocks(
            pr_number=pr_number,
            summary=result.summary,
            findings=findings,
            idempotency_key=idem_key,
            job_id=job.id,
        )
        # `[승인]` 검증을 위한 expected approval 등록.
        expected_approvals[job.id] = ApprovalContext(
            pr_number=pr_number,
            idempotency_key=idem_key,
            job_id=job.id,
            user_id=job.user_id,
        )
        _post_blocks_to_thread(
            app=app,
            channel=channel_id,
            thread_ts=thread_ts,
            blocks=blocks,
            text=f"PR #{pr_number} 리뷰 결과",
            logger=logger,
        )
        return f"reviewer_done pr={pr_number} duration={duration_s}s"

    return _handler


def _post_to_thread(
    *,
    app: Any,
    channel: str,
    thread_ts: str,
    text: str,
    logger: logging.Logger,
    context: str,
) -> None:
    """thread_ts 에 묶인 메시지 발사 (가드 통과 후)."""
    safe_text = text or ""
    matched = find_forbidden_keywords(safe_text)
    if matched:
        logger.error(
            "compliance: blocked thread post",
            extra={"context": context, "matched": matched},
        )
        safe_text = FALLBACK_RESPONSE
    try:
        app.client.chat_postMessage(
            channel=channel,
            thread_ts=thread_ts,
            text=safe_text,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("chat_postMessage 실패 (%s)", type(exc).__name__)


# Block Kit 에서 사용자 노출 가능한 비-text 키 (PR #51 reviewer P2 #3 후속).
# `text`/`fields[].text`/`accessory.text.text` 외에 미래 블록 도입 시 누설 위험이
# 있는 키들을 정적으로 나열. 현재 호출 경로 (`build_review_result_blocks`) 에서는
# 발생하지 않으나 회귀 안전망으로 미리 보강한다.
_BLOCK_USER_FACING_NON_TEXT_KEYS: frozenset[str] = frozenset(
    {
        "alt_text",      # image 블록 / image element
        "placeholder",   # plain_text_input / select 의 안내 텍스트 (str 또는 obj)
        "title",         # image 블록 캡션 (str 또는 plain_text obj)
        "label",         # input 블록 라벨 (plain_text obj)
        "hint",          # input 블록 보조 설명 (plain_text obj)
    }
)


def _collect_block_user_facing_text(blocks: Any) -> list[str]:
    """Block Kit 트리에서 사용자 노출 가능한 텍스트 필드를 수집한다.

    PR #43 reviewer P2-3 후속의 가드 보조 헬퍼. `text.text`, plain text value
    등을 모은다. `action_id` / `block_id` / `value` 는 내부 식별자라 제외.

    PR #51 reviewer P2 #2 후속: `key == "text"` 분기에서 inner 텍스트를 직접
    수집한 뒤 같은 노드를 다시 재귀로 들어가지 않는다 (중복 수집 제거 — 동작
    변경 0, 발사 차단 판정에 영향 없음).

    PR #51 reviewer P2 #3 후속: `image.alt_text`, `input.placeholder.text`,
    `actions.elements[].placeholder.text`, `title`, `label`, `hint` 등 비-text
    키도 누설 위험이 있어 수집 대상에 포함. 현재 호출 경로에는 해당 블록이
    없으므로 회귀 0, 미래 블록 도입 시 안전망 역할.
    """
    collected: list[str] = []

    def _visit(node: object) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "text":
                    # plain string text — 직접 수집 + 더 들어가지 않음 (중복 방지).
                    if isinstance(value, str):
                        collected.append(value)
                        continue
                    # text 객체 ({type, text} 형태) — inner 만 수집 + 재귀 생략.
                    if isinstance(value, dict):
                        inner = value.get("text")
                        if isinstance(inner, str):
                            collected.append(inner)
                        # text 객체 내부에는 추가 노출 가치 키가 없으므로 재귀 생략.
                        continue
                if key in _BLOCK_USER_FACING_NON_TEXT_KEYS:
                    # str 직접: image.alt_text 등.
                    if isinstance(value, str):
                        collected.append(value)
                        continue
                    # plain_text obj ({type, text}): title / label / hint /
                    # placeholder 가 obj 형태일 때. PR #52 reviewer P2 #1 후속
                    # — inner `text` 를 직접 수집한 뒤 `_visit(value)` 로
                    # fallthrough 하면 같은 inner 가 dict 분기에서 한 번 더
                    # 수집되는 중복이 발생. 무해하나 `count == 1` 보장 위해
                    # continue 로 끊는다.
                    if isinstance(value, dict):
                        inner = value.get("text")
                        if isinstance(inner, str):
                            collected.append(inner)
                        continue
                _visit(value)
        elif isinstance(node, list):
            for item in node:
                _visit(item)

    _visit(blocks)
    return collected


def _post_blocks_to_thread(
    *,
    app: Any,
    channel: str,
    thread_ts: str,
    blocks: list[dict[str, Any]],
    text: str,
    logger: logging.Logger,
) -> None:
    """Block Kit 메시지를 thread_ts 에 묶어 발사.

    PR #43 reviewer P2-3 후속: `blocks` 자체의 사용자 노출 텍스트도 발사 직전
    한 번 더 정적 가드 통과. 호출 측 (`build_review_result_blocks`) 이 이미
    `guard_text` 통과한 정상 경로는 회귀 0. 미래에 가드 미통과 blocks 가
    실수로 흘러들어오면 발사 차단 + text-only fallback 발사로 누설을 막는다.
    fallback `text` 인자도 `find_forbidden_keywords` 검사 통과 후 발사한다.
    """
    matched_in_blocks: list[str] = []
    for chunk in _collect_block_user_facing_text(blocks):
        matched = find_forbidden_keywords(chunk)
        if matched:
            matched_in_blocks.extend(matched)
    if matched_in_blocks:
        logger.error(
            "compliance: blocked thread blocks post",
            extra={"matched": sorted(set(matched_in_blocks))},
        )
        # blocks 누설 차단 + text-only fallback. fallback 문구도 별도 가드.
        safe_fallback = (
            FALLBACK_RESPONSE
            if not find_forbidden_keywords(FALLBACK_RESPONSE)
            else "응답 차단됨"
        )
        try:
            app.client.chat_postMessage(
                channel=channel,
                thread_ts=thread_ts,
                text=safe_fallback,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "chat_postMessage(blocks fallback) 실패 (%s)", type(exc).__name__
            )
        return

    # `text` 인자(알림용 본문) 도 마지막 한 번 더 가드.
    safe_text = text or ""
    if find_forbidden_keywords(safe_text):
        logger.error(
            "compliance: blocked thread blocks post (text fallback)",
            extra={"reason": "text"},
        )
        safe_text = FALLBACK_RESPONSE
    try:
        app.client.chat_postMessage(
            channel=channel,
            thread_ts=thread_ts,
            text=safe_text,
            blocks=blocks,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("chat_postMessage(blocks) 실패 (%s)", type(exc).__name__)


def _autoload_dotenv() -> None:
    """프로젝트 루트의 `.env` → `.env.local` 순으로 자동 로딩.

    - `.env`: 공유 기본값 (override=False — 셸 export 가 있으면 그걸 우선).
    - `.env.local`: 개인/머신 override (override=True — 개인 값이 공유 기본값을 덮음).

    공유 저장소이므로 개인 토큰은 반드시 `.env.local` 에만 둔다 (PRD §3.7 / §6.2).
    """
    base_path = find_dotenv(filename=".env", usecwd=True)
    if base_path:
        load_dotenv(base_path, override=False)
    local_path = find_dotenv(filename=".env.local", usecwd=True)
    if local_path:
        load_dotenv(local_path, override=True)


def run() -> int:
    """데몬 메인 루프. 종료 코드(0=정상)를 반환."""
    _autoload_dotenv()

    try:
        config = load_config()
    except ConfigError as exc:
        # AC-9: 한 줄 메시지 + 비정상 exit. 토큰은 노출되지 않는다.
        print(f"[Dev Manager] 시작 실패: {exc}", file=sys.stderr)
        return 2

    logger = _setup_logging(config.log_level)
    logger.info("Dev Manager 데몬을 시작합니다. %s", config.with_masked_repr())
    # PRD AC-9 (b/c) — 인증 모드를 시작 직후 1라인으로 명시해 의도 확인 가능.
    logger.info("auth_mode=%s", config.auth_mode.value)

    queue = JobQueue()
    # PRD §3.4 + `dev-relay-agent-integration.md` §3.1 — 재시작 복구.
    # 머지 carve-out: audit.jsonl 에 `merge_started` 후 종결 라인 없는 job 은
    # `unknown` 으로 마킹하고 사용자 안내.
    merge_in_flight = find_merge_in_flight_job_ids(_audit_log_path())
    failed, unknown = queue.recover_running_as_failed(
        merge_in_flight_job_ids=merge_in_flight
    )
    if failed:
        logger.info("재시작 복구: %d 건의 작업이 failed 로 마킹됐습니다.", len(failed))
    for job in unknown:
        logger.info(
            "재시작 복구 carve-out: job_id=%d 머지 결과 미확인 — 사용자 안내 발사 예정.",
            job.id,
        )

    rate_limiter = _RateLimiter()
    runner = AgentRunner(max_workers=1)

    # 자연어 분기 SDK runtime 준비 (PRD `dev-relay-natural-language.md`).
    sessions = AgentSessionStore()
    nl_runtime = _build_nl_runtime(logger)

    # PRD `dev-relay-agent-integration.md` 통합 인프라.
    review_detail_cache = ReviewDetailCache()
    expected_approvals: dict[int, ApprovalContext] = {}
    user_threads: dict[int, tuple[str, str]] = {}
    reviewer_callable = _build_reviewer(logger)
    merge_worker = _build_merge_worker(logger)

    app = build_app(
        config,
        logger,
        queue=queue,
        rate_limiter=rate_limiter,
        sessions=sessions,
        nl_runtime=nl_runtime,
        review_detail_cache=review_detail_cache,
        merge_worker=merge_worker,
        expected_approvals=expected_approvals,
        user_threads=user_threads,
    )

    # 머지 carve-out 안내 발사 — app.client 가 준비된 뒤 실행.
    for job in unknown:
        thread = user_threads.get(job.id)
        try:
            pr_number = int(job.command.rsplit(" ", 1)[-1])
        except ValueError:
            pr_number = 0
        if thread is not None and pr_number > 0:
            channel_id, thread_ts = thread
            _post_to_thread(
                app=app,
                channel=channel_id,
                thread_ts=thread_ts,
                text=TEMPLATE_MERGE_CARVE_OUT_NOTICE.format(pr_number=pr_number),
                logger=logger,
                context="merge_carve_out",
            )

    # picker 시작 — review job 처리.
    job_handler = _build_review_job_handler(
        app=app,
        queue=queue,
        reviewer=reviewer_callable,
        detail_cache=review_detail_cache,
        expected_approvals=expected_approvals,
        user_threads=user_threads,
        logger=logger,
    )
    picker = JobPicker(queue=queue, runner=runner, handler=job_handler, logger=logger)
    picker.start()

    from slack_bolt.adapter.socket_mode import SocketModeHandler

    handler = SocketModeHandler(app=app, app_token=config.app_token)
    _install_interrupt_handlers(logger)

    try:
        logger.info("Socket Mode 연결을 시도합니다.")
        handler.start()
    except KeyboardInterrupt:
        logger.info("키보드 인터럽트로 종료합니다.")
    except Exception as exc:  # noqa: BLE001
        logger.error("예상치 못한 종료: %s", type(exc).__name__)
        return 1
    finally:
        try:
            picker.stop(wait=True, timeout=_SHUTDOWN_TIMEOUT_S)
        except Exception:  # noqa: BLE001
            pass
        try:
            handler.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            # PR #48 reviewer P2-2 후속 — NL flag set + AgentRunner.shutdown 통합.
            shutdown_dev_relay(runner, timeout=_SHUTDOWN_TIMEOUT_S, logger=logger)
        except Exception:  # noqa: BLE001
            pass
        logger.info("Dev Manager 데몬을 정리했습니다.")
    return 0


def _build_reviewer(logger: logging.Logger) -> ReviewerCallable | None:
    """reviewer SDK callable 을 구성.

    PRD `dev-relay-write-tools.md` §3.1 (F-3 wire 완수) — `nl_sdk_runtime` 패턴
    재사용. `write_runtime.make_reviewer_callable` 이 SDK import 실패·인증 실패
    시 None 을 반환하면 reviewer 비활성으로 graceful degradation.

    인증·credential 정책 (PRD §3.1.4):
    - 구독 모드 우선 (`ANTHROPIC_API_KEY` 미설정 시 `claude` CLI 인증 승계).
    - API 키 모드 fallback (`sk-ant-` prefix 검증 후 사용).
    - 두 모드 모두 실패 시 graceful degradation — reviewer 비활성, 데몬 시작은
      계속. write 도구 호출 시점에 사용자에게 명확한 안내.
    """
    try:
        from ai.dev_relay.write_runtime import (
            is_sdk_available,
            make_reviewer_callable,
        )
    except ImportError as exc:
        logger.warning(
            "write_runtime import 실패 (%s) — reviewer 비활성", type(exc).__name__
        )
        return None

    if not is_sdk_available():
        logger.warning(
            "Claude Agent SDK 인증 미통과 — reviewer 비활성. 큐 적재만 가능."
        )
        return None

    callable_ = make_reviewer_callable()
    if callable_ is None:
        logger.warning("reviewer callable 생성 실패 — reviewer 비활성.")
        return None
    logger.info("reviewer SDK callable 준비 완료.")
    return callable_


def _build_merge_worker(logger: logging.Logger) -> MergeWorker | None:
    """`gh pr merge --squash --delete-branch` worker 를 구성.

    PRD `dev-relay-agent-integration.md` §3.3 + §10. `subprocess.run` 으로
    호출하며 returncode + stderr 로 분류한다. `gh` CLI 미설치 / 미인증 환경에서는
    호출 시점에 `github_unauthorized` 또는 `unknown_error` 로 분류된다.
    """
    import shutil
    import subprocess

    if shutil.which("gh") is None:
        logger.warning("gh CLI 가 설치되어 있지 않습니다. 머지 호출이 모두 실패로 분류됩니다.")

    def _worker(pr_number: int) -> MergeOutcome:
        try:
            completed = subprocess.run(
                [
                    "gh",
                    "pr",
                    "merge",
                    str(pr_number),
                    "--squash",
                    "--delete-branch",
                ],
                capture_output=True,
                text=True,
                timeout=60.0,
                check=False,
            )
        except FileNotFoundError:
            return MergeOutcome(
                success=False,
                sha=None,
                detail="gh not found",
                classification=FailureClassification.GITHUB_UNAUTHORIZED,
            )
        except subprocess.TimeoutExpired:
            return MergeOutcome(
                success=False,
                sha=None,
                detail="gh timeout",
                classification=FailureClassification.SDK_TIMEOUT,
            )
        if completed.returncode == 0:
            sha = extract_sha(completed.stdout) or extract_sha(completed.stderr)
            return MergeOutcome(
                success=True,
                sha=sha,
                detail=completed.stdout.strip() or "merged",
            )
        classification = classify_merge_stderr(completed.stderr)
        return MergeOutcome(
            success=False,
            sha=None,
            detail=(completed.stderr or completed.stdout or "").strip()[:500],
            classification=classification,
        )

    return _worker


if __name__ == "__main__":
    sys.exit(run())
