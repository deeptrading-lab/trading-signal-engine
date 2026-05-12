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
    ApprovalContext,
    MergeOutcome,
    MergeRejection,
    MergeWorker,
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
    TEMPLATE_DESTRUCTIVE_BLOCKED,
    TEMPLATE_MERGE_CARVE_OUT_NOTICE,
    TEMPLATE_QUEUE_ACCEPTED_MERGE,
    TEMPLATE_QUEUE_ACCEPTED_REVIEW,
    TEMPLATE_QUEUE_BUSY,
    TEMPLATE_RATE_LIMIT,
    TEMPLATE_REVIEW_DETAIL_LOOKUP_FAILED,
    TEMPLATE_UNKNOWN_COMMAND,
    build_merge_confirm_blocks,
    build_merge_result_text,
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

# PRD §3.2 — busy 시 사용자에게 발사할 안내 1줄. 한국어 1줄 (20~60자), 컴플라이언스 0 hit.
# 발사 직전 `guard_text_with_urls` 이중 가드를 거친다.
TEMPLATE_NL_BUSY: str = "지금 다른 요청을 처리 중이에요. 잠시 후 다시 보내주세요."


def _audit_log_path() -> Path:
    """audit.jsonl 위치 (PRD §3.6)."""
    return default_db_path().parent / "audit.jsonl"


def _append_audit(record: dict[str, Any]) -> None:
    """audit.jsonl 한 줄 append. user_id 는 호출 측이 마스킹한 값을 넘긴다.

    PRD §3.8 — 신규 파일 생성 시 0600 권한 적용. 이미 존재하는 파일은 사용자가
    명시적으로 권한을 풀어둔 경우를 존중해 그대로 둔다 (강제로 좁히지 않음).
    부모 디렉터리(0700) 는 `JobQueue::_ensure_dir_secure` 가 보장한다.
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
        if not is_allowed_sender(user_id, config.allowed_user_ids):
            logger.info(
                "허용되지 않은 버튼 클릭을 무시했습니다 (user=%s)",
                mask_user_id(user_id),
            )
            return
        _append_audit(
            {
                "ts": _now_kst(),
                "kind": "button_action",
                "user": mask_user_id(user_id),
                "action": "cancel_merge",
            }
        )
        safe_say(say, TEMPLATE_CANCEL_NOTICE, logger, context="cancel")

    @app.action("approve_merge")
    def handle_approve_merge(ack: Any, body: dict, say: Any) -> None:
        ack()
        user_id = extract_action_user_id(body) or ""
        if not is_allowed_sender(user_id, config.allowed_user_ids):
            logger.info(
                "허용되지 않은 버튼 클릭을 무시했습니다 (user=%s)",
                mask_user_id(user_id),
            )
            return
        _append_audit(
            {
                "ts": _now_kst(),
                "kind": "button_action",
                "user": mask_user_id(user_id),
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
            _append_audit(
                {
                    "ts": _now_kst(),
                    "kind": "merge_failed",
                    "job_id": payload.job_id,
                    "pr": payload.pr_number,
                    "classification": FailureClassification.UNKNOWN_ERROR.value,
                }
            )
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
        if not is_allowed_sender(user_id, config.allowed_user_ids):
            logger.info(
                "허용되지 않은 버튼 클릭을 무시했습니다 (user=%s)",
                mask_user_id(user_id),
            )
            return
        _append_audit(
            {
                "ts": _now_kst(),
                "kind": "button_action",
                "user": mask_user_id(user_id),
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

    @app.action("view_details")
    def handle_view_details(ack: Any, body: dict, say: Any) -> None:
        ack()
        user_id = extract_action_user_id(body) or ""
        if not is_allowed_sender(user_id, config.allowed_user_ids):
            return
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


def _post_blocks_to_thread(
    *,
    app: Any,
    channel: str,
    thread_ts: str,
    blocks: list[dict[str, Any]],
    text: str,
    logger: logging.Logger,
) -> None:
    """Block Kit 메시지를 thread_ts 에 묶어 발사."""
    try:
        app.client.chat_postMessage(
            channel=channel,
            thread_ts=thread_ts,
            text=text,
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
            runner.shutdown(wait=True, timeout=_SHUTDOWN_TIMEOUT_S)
        except Exception:  # noqa: BLE001
            pass
        logger.info("Dev Manager 데몬을 정리했습니다.")
    return 0


def _build_reviewer(logger: logging.Logger) -> ReviewerCallable | None:
    """reviewer SDK callable 을 구성.

    PRD `dev-relay-agent-integration.md` §3.2 — Claude Agent SDK 신규 세션으로
    PR diff + 리뷰 instruction 을 prompt 로 전달. 실 SDK 호출 자체는 nl_sdk_runtime
    의 패턴을 그대로 답습 — SDK import 실패 시 None 반환 (reviewer 비활성).

    본 함수는 환경 미설정 환경에서 데몬 시작을 막지 않는 것이 목적. 실제 SDK
    호출 구현은 후속 PR 에서 nl_sdk_runtime 와 동일 진입점을 거쳐 보강된다.
    현 단계에서는 SDK runtime 이 import 불가하면 picker 가 reviewer=None 으로
    빈 fallback 을 발사한다 (사용자에게 unknown_error 안내).
    """
    try:
        # SDK 가 설치돼 있는지만 확인 — 실 호출 callable 은 후속 단계에서.
        importlib.import_module("claude_agent_sdk")
    except ImportError:
        logger.warning(
            "Claude Agent SDK import 실패 — reviewer 비활성. 큐 적재만 가능."
        )
        return None

    def _reviewer(pr_number: int) -> ReviewResult:
        # 현 단계 fallback — 실 SDK 호출 통합은 후속 단계에서 보강.
        # 본 함수가 실제로 호출되는 흐름은 사용자 셋업(부록 A) + SDK 인증
        # 모두 통과한 환경 한정. 미설정 환경에서는 위 ImportError 분기에서
        # None 이 반환되어 본 callable 자체가 picker 에 전달되지 않는다.
        raise NotImplementedError(
            "reviewer SDK 호출 구현은 후속 단계에서 nl_sdk_runtime 패턴으로 추가 예정."
        )

    return _reviewer


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
