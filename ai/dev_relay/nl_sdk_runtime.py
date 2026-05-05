"""
SDK 실호출 wrapper — 자연어 분기 (Phase 1 read-only).

PRD: docs/prd/dev-relay-natural-language.md §3.2 / §3.3 / §3.4

본 모듈은 `claude_agent_sdk` 를 실제로 import 하고 호출한다. 호출은 사용자 셋업
(부록 A) 이후의 수동 검증 단계에서만 발생하며, 단위 테스트는 본 모듈을 import
하지 않는다 (SDK 가 사이드이펙트 없이 import 가능하면 import 자체는 안전하지만,
호출 자체는 mock 으로 대체).

설계
- `make_classifier` — Haiku 분류 callable 을 반환.
- `make_haiku_responder` — Haiku 짧은 응답 callable.
- `make_sonnet_responder` — Sonnet 본 응답 callable. PreToolUse hook 이 도구
  화이트리스트를 강제한다. session_id resume 도 본 함수 내부에서 처리.

callable 구현은 매 호출마다 SDK 의 `query()` 또는 `ClaudeSDKClient` 를 사용한다.
구독 모드 / API 키 모드 모두 SDK 가 자동 판별 (config 가 ANTHROPIC_API_KEY 처리).
"""

from __future__ import annotations

import logging
from typing import Any

from ai.dev_relay.nl_agent import (
    HaikuResponse,
    SonnetResponse,
)
from ai.dev_relay.nl_classifier import (
    CLASSIFY_SYSTEM_PROMPT,
    MODEL_HAIKU_ID,
    MODEL_SONNET_ID,
    ClassificationResult,
    parse_label,
)
from ai.dev_relay.tool_policy import ALLOWED_TOOLS, ToolDecision, evaluate

_LOGGER = logging.getLogger("ai.dev_relay.nl_sdk_runtime")

# Sonnet 본 응답 시스템 프롬프트 — 도구 결과를 종합한 보고만 한다.
# 외부 노출되지 않으므로 한국어로 작성.
SONNET_SYSTEM_PROMPT: str = (
    "당신은 사용자(이하영)의 로컬 개발 비서입니다. "
    "사용자의 자연어 요청에 대해 read-only 도구로 정보를 수집한 뒤 종합해 보고합니다. "
    "다음 규칙을 반드시 지켜주세요.\n"
    "- 화이트리스트 외 도구 호출은 거부됩니다. 호출이 거부되면 그 사실을 사용자에게 안내합니다.\n"
    "- 어떤 경우에도 파일을 수정·생성하거나 git 변경 작업(commit/push/merge/reset 등) 을 시도하지 않습니다.\n"
    "- 비밀 파일(.env, secrets/, *token*, *credential*) 은 읽지 않습니다.\n"
    "- 외부 가시 텍스트에 이 저장소의 도메인 영역 키워드를 평문으로 노출하지 않습니다 — "
    "GitHub URL 안에 들어가는 슬러그는 예외이지만 본문 산문에서는 일반 표현을 사용하세요.\n"
    "- 응답은 한국어로, Slack 섹션 블록에 표시할 수 있는 마크다운으로 작성합니다.\n"
    "- 응답 본문에 git push --force / git reset --hard 같은 위험 명령을 권장하지 않습니다."
)

HAIKU_SHORT_RESPOND_SYSTEM_PROMPT: str = (
    "당신은 짧은 응답 비서입니다. 한 줄로 친절히 답변하세요. "
    "위험한 작업 (git reset --hard, .env 출력 등) 요청에는 정중히 거부하고 "
    "사용자가 직접 PC 에서 처리하도록 안내합니다."
)


def _build_pre_tool_use_hook(
    *,
    audit_recorder: Any,
    user_id_masked: str,
    now_iso: Any,
):
    """SDK PreToolUse hook callback factory.

    audit_recorder 는 audit.jsonl 에 한 줄 append 하는 callable. 본 hook 은
    `tool_policy.evaluate` 결과에 따라 deny/allow 를 SDK 에 돌려준다.
    """
    from claude_agent_sdk import PreToolUseHookInput
    from claude_agent_sdk.types import SyncHookJSONOutput

    async def _hook(
        input_data: PreToolUseHookInput,
        tool_use_id: str | None,
        context: Any,
    ) -> SyncHookJSONOutput:
        tool_name = input_data.get("tool_name", "")
        tool_input = input_data.get("tool_input", {})
        decision: ToolDecision = evaluate(tool_name, tool_input)

        if decision.allowed:
            audit_recorder(
                {
                    "ts": now_iso(),
                    "kind": "tool_call",
                    "stage": "respond",
                    "tool": tool_name,
                    "brief": decision.brief,
                }
            )
            return {}

        audit_recorder(
            {
                "ts": now_iso(),
                "kind": "tool_denied",
                "stage": "respond",
                "tool": tool_name,
                "reason": decision.reason or "not_whitelisted",
                "brief": decision.brief,
            }
        )
        # SDK 가 deny 결정을 인식하도록 hookSpecificOutput 또는 decision 필드를
        # 통해 응답한다. 0.1.x SDK 의 정확한 deny 키 이름은 SDK 문서를 따른다.
        return {
            "decision": "block",
            "reason": f"Phase 1 read-only: {decision.reason}",
        }

    return _hook


def make_classifier(
    *,
    cwd: str | None = None,
):
    """Haiku 분류 callable 생성. SDK `query()` 사용.

    반환 callable 은 (system_prompt, user_text) → ClassificationResult.
    실 호출 시 SDK 의 `query()` 를 max_turns=1, model=Haiku 로 사용한다.
    """
    from claude_agent_sdk import (
        AssistantMessage,
        ClaudeAgentOptions,
        TextBlock,
        query,
    )

    def _classify(system_prompt: str, user_text: str) -> ClassificationResult:
        # 시스템 프롬프트는 호출 측에서 받은 값을 그대로 사용 — prompt injection
        # 격리 (사용자 텍스트는 user role 로만 들어간다).
        options = ClaudeAgentOptions(
            model=MODEL_HAIKU_ID,
            system_prompt=system_prompt or CLASSIFY_SYSTEM_PROMPT,
            allowed_tools=[],  # 분류에는 도구 불필요.
            max_turns=1,
            cwd=cwd,
        )
        text_pieces: list[str] = []

        async def _drain():
            async for message in query(prompt=user_text, options=options):
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            text_pieces.append(block.text)

        import asyncio

        asyncio.run(_drain())
        raw = "".join(text_pieces).strip()
        return ClassificationResult(label=parse_label(raw))

    return _classify


def make_haiku_responder(*, cwd: str | None = None):
    """Haiku 짧은 응답 callable.

    반환 callable 은 (user_text) → HaikuResponse.
    """
    from claude_agent_sdk import (
        AssistantMessage,
        ClaudeAgentOptions,
        TextBlock,
        query,
    )

    def _respond(user_text: str) -> HaikuResponse:
        options = ClaudeAgentOptions(
            model=MODEL_HAIKU_ID,
            system_prompt=HAIKU_SHORT_RESPOND_SYSTEM_PROMPT,
            allowed_tools=[],
            max_turns=1,
            cwd=cwd,
        )
        chunks: list[str] = []

        async def _drain():
            async for message in query(prompt=user_text, options=options):
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            chunks.append(block.text)

        import asyncio

        asyncio.run(_drain())
        return HaikuResponse(text="".join(chunks).strip())

    return _respond


def make_sonnet_responder(
    *,
    audit_recorder: Any,
    user_id_masked: str,
    now_iso: Any,
    cwd: str | None = None,
):
    """Sonnet 본 응답 callable — PreToolUse hook + 세션 resume 통합.

    반환 callable 은 (user_text, resume_session_id|None) → SonnetResponse.
    """
    from claude_agent_sdk import (
        AssistantMessage,
        ClaudeAgentOptions,
        HookMatcher,
        ResultMessage,
        TextBlock,
        query,
    )

    pre_tool_use_hook = _build_pre_tool_use_hook(
        audit_recorder=audit_recorder,
        user_id_masked=user_id_masked,
        now_iso=now_iso,
    )

    def _respond(
        user_text: str, resume_session_id: str | None
    ) -> SonnetResponse:
        options = ClaudeAgentOptions(
            model=MODEL_SONNET_ID,
            system_prompt=SONNET_SYSTEM_PROMPT,
            allowed_tools=sorted(ALLOWED_TOOLS),
            disallowed_tools=["Edit", "Write", "NotebookEdit"],
            max_turns=10,
            resume=resume_session_id,
            hooks={
                "PreToolUse": [HookMatcher(matcher=None, hooks=[pre_tool_use_hook])]
            },
            cwd=cwd,
        )
        chunks: list[str] = []
        sid: str | None = None

        async def _drain():
            nonlocal sid
            async for message in query(prompt=user_text, options=options):
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            chunks.append(block.text)
                elif isinstance(message, ResultMessage):
                    sid = getattr(message, "session_id", None) or sid

        import asyncio

        asyncio.run(_drain())
        return SonnetResponse(
            text="".join(chunks).strip(),
            session_id=sid,
        )

    return _respond


__all__ = [
    "HAIKU_SHORT_RESPOND_SYSTEM_PROMPT",
    "SONNET_SYSTEM_PROMPT",
    "make_classifier",
    "make_haiku_responder",
    "make_sonnet_responder",
]
