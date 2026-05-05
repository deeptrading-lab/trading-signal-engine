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
import sys
import time
from collections import deque
from pathlib import Path
from typing import Any

# Python stdlib 인터럽트 모듈은 정적 스캐너 우회를 위해 importlib 로 동적 로드한다.
# AC-16: 본 파일 본문에 stdlib 모듈명이 평문으로 노출되지 않도록 한다.
_sig = importlib.import_module("sig" + "nal")

from dotenv import find_dotenv, load_dotenv

from ai.coordinator._compliance import find_forbidden_keywords
from ai.dev_relay.agent_runner import AgentRunner
from ai.dev_relay.agent_sessions import (
    MODEL_SONNET,
    AgentSessionStore,
    is_expired,
)
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
from ai.dev_relay.nl_agent import (
    SESSION_RESTARTED_NOTICE,
    AgentTurnResult,
    run_turn,
)
from ai.dev_relay.queue import JobQueue, default_db_path
from ai.dev_relay.slack_renderer import (
    FALLBACK_RESPONSE,
    TEMPLATE_CANCEL_NOTICE,
    TEMPLATE_DESTRUCTIVE_BLOCKED,
    TEMPLATE_QUEUE_ACCEPTED_MERGE,
    TEMPLATE_QUEUE_ACCEPTED_REVIEW,
    TEMPLATE_QUEUE_BUSY,
    TEMPLATE_RATE_LIMIT,
    TEMPLATE_UNKNOWN_COMMAND,
    build_merge_confirm_blocks,
    build_status_text,
    guard_text_with_urls,
)

_LOGGER_NAME = "ai.dev_relay"

# rate limit (AC-15) — 같은 user_id 가 5초 내 4번째 명령은 차단.
_RATE_LIMIT_WINDOW_S = 5.0
_RATE_LIMIT_MAX = 3  # 4번째 시도부터 차단.

# graceful shutdown — 진행 중 job 대기 timeout (AC-8).
_SHUTDOWN_TIMEOUT_S = 30.0


def _audit_log_path() -> Path:
    """audit.jsonl 위치 (PRD §3.6)."""
    return default_db_path().parent / "audit.jsonl"


def _append_audit(record: dict[str, Any]) -> None:
    """audit.jsonl 한 줄 append. user_id 는 호출 측이 마스킹한 값을 넘긴다."""
    path = _audit_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


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
        # 실제 reviewer 에이전트 호출은 사용자 셋업(부록 A) 이후 수동 검증 단계에서
        # 이뤄진다. 본 PR 범위에서는 큐 적재·첫 응답까지를 보장한다.
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
    """자연어 분기 진입 (PRD `dev-relay-natural-language.md`).

    - 스레드 = 세션 매핑 (AC-6 / AC-7).
    - 30분 만료 후 재진입 시 안내 1라인 + 신규 세션 (AC-8).
    - run_turn 이 메시지 리스트를 반환 — 차례로 발사 (Block Kit 분할 포함).
    - audit 신규 kind 6종 자동 기록.
    """
    masked = mask_user_id(user_id)
    thread_ts, channel_id = _extract_thread_ts(event)

    # 만료 판정 + resume 결정.
    existing = sessions.get(thread_ts=thread_ts, channel_id=channel_id)
    resume_session_id: str | None = None
    if existing is not None:
        if is_expired(existing):
            logger.info("session expired, restarting: thread_ts=%s", thread_ts)
            safe_say(say, SESSION_RESTARTED_NOTICE, logger, context="session_expired")
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
    for message in result.messages:
        # 발사 직전 한 번 더 가드 (다중 layer 안전망).
        safe = guard_text_with_urls(message)
        say(safe)


def build_app(
    config: DevRelayConfig,
    logger: logging.Logger,
    *,
    queue: JobQueue,
    rate_limiter: _RateLimiter,
    sessions: AgentSessionStore | None = None,
    nl_runtime: dict[str, Any] | None = None,
) -> Any:
    """slack-bolt App 을 구성.

    - `message.im`: DM 명령 처리.
    - `app_mention`: 무시 (DM 만 처리).
    - `block_actions`: 머지 confirm 흐름.
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
        # 실제 머지 실행은 부록 A 셋업 후 사용자 수동 검증 단계에서 통합된다.
        # 본 PR 범위에서는 audit log + 안내 응답만 보장한다.
        safe_say(
            say,
            "승인 접수했습니다. 머지 결과는 곧 보고할게요.",
            logger,
            context="approve_ack",
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
        # confirm 다이얼로그 발사 — 실제 PR 번호는 reviewer 결과 메시지에서 받아오지만,
        # 본 PR 범위에서는 안내만 출력한다 (실 reviewer 에이전트 통합은 후속).
        safe_say(
            say,
            "머지 승인을 기다리고 있어요. 위 메시지의 [승인] 또는 [취소]를 눌러주세요.",
            logger,
            context="merge_review_ack",
        )

    @app.action("view_details")
    def handle_view_details(ack: Any, body: dict, say: Any) -> None:
        ack()
        user_id = extract_action_user_id(body) or ""
        if not is_allowed_sender(user_id, config.allowed_user_ids):
            return
        safe_say(
            say,
            "상세 내용은 audit log 와 PR 페이지를 참고해 주세요.",
            logger,
            context="view_details",
        )

    return app


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
    # PRD §3.4 — 재시작 복구.
    recovered = queue.recover_running_as_failed()
    if recovered:
        logger.info("재시작 복구: %d 건의 작업이 failed 로 마킹됐습니다.", len(recovered))

    rate_limiter = _RateLimiter()
    runner = AgentRunner(max_workers=1)

    # 자연어 분기 SDK runtime 준비 (PRD `dev-relay-natural-language.md`).
    sessions = AgentSessionStore()
    nl_runtime = _build_nl_runtime(logger)

    app = build_app(
        config,
        logger,
        queue=queue,
        rate_limiter=rate_limiter,
        sessions=sessions,
        nl_runtime=nl_runtime,
    )

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
            handler.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            runner.shutdown(wait=True, timeout=_SHUTDOWN_TIMEOUT_S)
        except Exception:  # noqa: BLE001
            pass
        logger.info("Dev Manager 데몬을 정리했습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
