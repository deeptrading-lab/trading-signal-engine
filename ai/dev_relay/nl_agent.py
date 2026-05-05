"""
자연어 분기 에이전트 루프 (Dev Manager Phase 1, read-only).

PRD: docs/prd/dev-relay-natural-language.md §2 ~ §3.7

흐름
- dispatcher fast-path 미스 후 진입.
- (1) Haiku 분류 → 라벨에 따라
  - STATUS_LIKE / UNKNOWN_OR_DESTRUCTIVE → Haiku 짧은 응답 (plain text).
  - SUMMARY_REQUEST / REPORT_REQUEST → Sonnet read-only 도구 루프 (Block Kit).
- (2) 발사 직전 컴플라이언스 가드 (`guard_text_with_urls`) + destructive 가드.
- (3) audit log 1라인 기록 (PRD §3.7 신규 kind 6종).

본 모듈은 SDK 호출 자체를 수행하지 않는다 (테스트 가능성). 호출 측 (`main`) 이
HaikuRespondCallable / SonnetRespondCallable 두 callable 을 주입한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Protocol

from ai.dev_relay.agent_runner import (
    DestructiveOperationBlocked,
    assert_no_destructive_intent,
)
from ai.dev_relay.nl_classifier import (
    ClassificationResult,
    ClassifierCallable,
    IntentLabel,
    classify,
    routes_to_sonnet,
)
from ai.dev_relay.slack_renderer import (
    FALLBACK_RESPONSE,
    guard_text_with_urls,
)


# Slack 4000자 한도 — 본 PRD 는 안전하게 3500자로 분할.
BLOCK_KIT_TEXT_BUDGET: int = 3500

# Phase 1 사용자 안내 문구.
TOOL_DENIED_NOTICE: str = "이 도구는 Phase 1 범위 밖이라 봇이 거부했습니다."
SESSION_RESTARTED_NOTICE: str = (
    "이 스레드 세션이 30분 이상 유휴 상태라 새 세션으로 다시 시작했어요."
)


class ResponseStage(str, Enum):
    """LLM 호출 단계 — audit log 의 stage 필드."""

    CLASSIFY = "classify"
    RESPOND = "respond"


@dataclass(frozen=True, slots=True)
class HaikuResponse:
    """Haiku 짧은 응답 결과."""

    text: str
    prompt_tokens: int = 0
    response_tokens: int = 0


@dataclass(frozen=True, slots=True)
class SonnetResponse:
    """Sonnet 본 응답 결과.

    `tool_calls` 는 (tool_name, brief, allowed) 튜플 리스트 — audit log 기록용.
    """

    text: str
    prompt_tokens: int = 0
    response_tokens: int = 0
    tool_calls: list[tuple[str, str, bool]] = field(default_factory=list)
    session_id: str | None = None


# Callable 시그니처 — 외부에서 SDK 호출을 주입.
HaikuRespondCallable = Callable[[str], HaikuResponse]
SonnetRespondCallable = Callable[[str, str | None], SonnetResponse]


@dataclass(frozen=True, slots=True)
class AgentTurnResult:
    """한 turn 의 처리 결과 — 발사할 메시지와 audit 메타.

    `messages` 는 발사 순서대로의 텍스트 페이로드 리스트. 호출 측이 차례로
    `safe_say` 등으로 발사한다.
    """

    label: IntentLabel
    stage_used: list[str]  # ["classify", "respond"] 등
    messages: list[str]
    sonnet_session_id: str | None = None
    classification: ClassificationResult | None = None
    haiku_response: HaikuResponse | None = None
    sonnet_response: SonnetResponse | None = None
    response_blocked_reason: str | None = None


# ---------------------------------------------------------------------------
# Block Kit 분할
# ---------------------------------------------------------------------------


def split_for_block_kit(
    text: str,
    *,
    budget: int = BLOCK_KIT_TEXT_BUDGET,
) -> list[str]:
    """긴 응답을 Slack 4000자 한도에 맞춰 chunk 로 분할.

    - budget 이하의 텍스트는 단일 chunk.
    - 줄바꿈 경계로 우선 분할, 줄 단독으로 budget 초과 시 강제 분할.
    """
    if not text:
        return []
    if len(text) <= budget:
        return [text]

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for line in text.splitlines(keepends=True):
        if len(line) > budget:
            # 단일 줄이 너무 긴 경우: 누적 flush 후 강제 분할.
            if current:
                chunks.append("".join(current))
                current = []
                current_len = 0
            for i in range(0, len(line), budget):
                chunks.append(line[i : i + budget])
            continue
        if current_len + len(line) > budget:
            chunks.append("".join(current))
            current = [line]
            current_len = len(line)
        else:
            current.append(line)
            current_len += len(line)
    if current:
        chunks.append("".join(current))
    return chunks


# ---------------------------------------------------------------------------
# 응답 발사 직전 가드
# ---------------------------------------------------------------------------


def guard_response_text(text: str | None) -> tuple[str, str | None]:
    """응답 텍스트를 발사 전 검사.

    반환: (안전한 텍스트, 차단 사유 또는 None).
    - destructive 표지 검출 → fallback + reason="destructive".
    - 컴플라이언스 키워드 검출 (URL escape 후) → fallback + reason="compliance".
    - 통과 시 (URL 원복된 텍스트, None).
    """
    if not text:
        return text or "", None
    try:
        assert_no_destructive_intent(text, context="nl_response")
    except DestructiveOperationBlocked:
        return FALLBACK_RESPONSE, "destructive"

    safe = guard_text_with_urls(text)
    if safe == FALLBACK_RESPONSE and text != FALLBACK_RESPONSE:
        return FALLBACK_RESPONSE, "compliance"
    return safe, None


# ---------------------------------------------------------------------------
# Audit log 기록 — Protocol 로 외부 주입
# ---------------------------------------------------------------------------


class AuditSink(Protocol):
    """audit.jsonl 한 줄 append 콜백."""

    def __call__(self, record: dict[str, Any]) -> None: ...


# ---------------------------------------------------------------------------
# 메인 엔트리 — 한 turn 처리
# ---------------------------------------------------------------------------


def run_turn(
    *,
    user_text: str,
    user_id_masked: str,
    classifier: ClassifierCallable,
    haiku_responder: HaikuRespondCallable,
    sonnet_responder: SonnetRespondCallable,
    resume_session_id: str | None = None,
    audit: AuditSink,
    now_iso: Callable[[], str],
) -> AgentTurnResult:
    """자연어 분기 한 turn 을 실행한다.

    - 분류 단계는 항상 호출.
    - 결과 라벨에 따라 Haiku 또는 Sonnet 응답 callable 실행.
    - 발사할 메시지 리스트를 `AgentTurnResult.messages` 에 담아 반환 — 호출 측이
      차례로 발사한다 (Sonnet 분기는 분할 chunk 여러 개일 수 있다).
    - audit log 신규 kind 6종을 본 함수가 모두 기록한다.

    호출 측 책임:
    - 화이트리스트 / rate limit / destructive 1차 차단은 dispatcher 단에서 처리.
    - 본 함수는 fast-path 미스 후에만 호출된다.
    """
    stage_used: list[str] = []
    messages: list[str] = []

    # (1) Haiku 분류.
    classification = classify(user_text, classifier=classifier)
    stage_used.append(ResponseStage.CLASSIFY.value)

    audit(
        {
            "ts": now_iso(),
            "kind": "llm_invoked",
            "user": user_id_masked,
            "stage": ResponseStage.CLASSIFY.value,
            "model": "haiku-4-5",
            "prompt_tokens": classification.prompt_tokens,
            "response_tokens": classification.response_tokens,
        }
    )
    audit(
        {
            "ts": now_iso(),
            "kind": "llm_classified",
            "user": user_id_masked,
            "label": classification.label.value,
            "input_chars": len(user_text or ""),
        }
    )

    # (2) 라우팅 분기.
    if not routes_to_sonnet(classification.label):
        # Haiku 짧은 응답 분기.
        haiku = haiku_responder(user_text)
        stage_used.append(ResponseStage.RESPOND.value)
        audit(
            {
                "ts": now_iso(),
                "kind": "llm_invoked",
                "user": user_id_masked,
                "stage": ResponseStage.RESPOND.value,
                "model": "haiku-4-5",
                "prompt_tokens": haiku.prompt_tokens,
                "response_tokens": haiku.response_tokens,
            }
        )
        safe_text, blocked = guard_response_text(haiku.text)
        if blocked:
            audit(
                {
                    "ts": now_iso(),
                    "kind": "llm_response_blocked",
                    "user": user_id_masked,
                    "reason": blocked,
                }
            )
        messages.append(safe_text or FALLBACK_RESPONSE)
        return AgentTurnResult(
            label=classification.label,
            stage_used=stage_used,
            messages=messages,
            classification=classification,
            haiku_response=haiku,
            response_blocked_reason=blocked,
        )

    # Sonnet 본 응답 분기.
    sonnet = sonnet_responder(user_text, resume_session_id)
    stage_used.append(ResponseStage.RESPOND.value)
    audit(
        {
            "ts": now_iso(),
            "kind": "llm_invoked",
            "user": user_id_masked,
            "stage": ResponseStage.RESPOND.value,
            "model": "sonnet-4-6",
            "prompt_tokens": sonnet.prompt_tokens,
            "response_tokens": sonnet.response_tokens,
        }
    )
    for tool_name, brief, allowed in sonnet.tool_calls:
        kind = "tool_call" if allowed else "tool_denied"
        record: dict[str, Any] = {
            "ts": now_iso(),
            "kind": kind,
            "stage": ResponseStage.RESPOND.value,
            "tool": tool_name,
            "brief": brief,
        }
        if not allowed:
            record["reason"] = "phase1_readonly"
        audit(record)

    safe_text, blocked = guard_response_text(sonnet.text)
    if blocked:
        audit(
            {
                "ts": now_iso(),
                "kind": "llm_response_blocked",
                "user": user_id_masked,
                "reason": blocked,
            }
        )
        messages.append(safe_text or FALLBACK_RESPONSE)
    else:
        for chunk in split_for_block_kit(safe_text):
            messages.append(chunk)

    return AgentTurnResult(
        label=classification.label,
        stage_used=stage_used,
        messages=messages,
        sonnet_session_id=sonnet.session_id,
        classification=classification,
        sonnet_response=sonnet,
        response_blocked_reason=blocked,
    )


__all__ = [
    "AgentTurnResult",
    "BLOCK_KIT_TEXT_BUDGET",
    "HaikuResponse",
    "HaikuRespondCallable",
    "SESSION_RESTARTED_NOTICE",
    "SonnetResponse",
    "SonnetRespondCallable",
    "TOOL_DENIED_NOTICE",
    "guard_response_text",
    "run_turn",
    "split_for_block_kit",
]
