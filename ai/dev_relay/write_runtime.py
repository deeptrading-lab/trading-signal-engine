"""
SDK 호출 wrapper — write 도구 (patch / 커밋 메시지 자동 생성) + reviewer wire.

PRD: docs/prd/dev-relay-write-tools.md §3.1 / §3.2

본 모듈은 `nl_sdk_runtime.py` 패턴을 재사용해 SDK 신규 세션 호출 callable 을
구성한다. 자연어 분기와 별도 세션이며, write 도구의 SDK 호출은 신규 컨텍스트.

호출 측 (`main._build_reviewer`, write 명령 핸들러) 이 본 모듈의 factory 를 호출해
callable 을 얻은 뒤 picker / 명령 핸들러에서 호출한다.

SDK import 실패 / 인증 실패 시 callable factory 는 `None` 을 반환하거나 callable
이 명확한 분류 (`unknown_error`) 로 raise — 데몬 시작 자체는 막지 않는다.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable


# PR #59 reviewer P1-3 후속 — NL → structured 변환 SDK 호출 timeout.
# `_handle_nl_write_conversion` 이 메시지 핸들러 thread 에서 `_nl_turn_lock` 보유
# 중 동기 호출하므로, SDK hang 시 NL 분기 전체가 영구 차단된다. 본 timeout 은
# 그 가능성을 0 으로 만들기 위한 상한. 1~2주 모니터링 후 조정.
WRITE_CONVERTER_TIMEOUT_SECONDS: float = 30.0


class WriteConverterTimeout(Exception):
    """write converter SDK 호출 timeout — 호출 측이 명시 분류로 처리.

    `write_classifier.convert` 가 본 예외를 잡아 `ConversionFailReason.TIMEOUT`
    으로 매핑한다.
    """

from ai.dev_relay.nl_classifier import MODEL_HAIKU_ID, MODEL_SONNET_ID
from ai.dev_relay.reviewer import ReviewResult

_LOGGER = logging.getLogger("ai.dev_relay.write_runtime")


# reviewer 시스템 프롬프트 — 코드 퀄리티 / 아키텍처 / 클린 코드 / 보안 관점.
# 외부 노출되지 않으므로 한국어로 작성. 도메인 키워드 0 hit.
REVIEWER_SYSTEM_PROMPT: str = (
    "당신은 사용자(이하영)의 PR 리뷰어입니다. 다음 관점으로 PR 을 검토하고 "
    "한국어로 보고합니다.\n"
    "- 코드 퀄리티: 가독성, 명명, 함수 분리\n"
    "- 아키텍처: 모듈 경계, 의존성 방향, 단일 책임\n"
    "- 보안: 비밀 노출, 외부 입력 검증\n"
    "- 클린 코드: 중복 제거, 매직 넘버, 주석 적절성\n\n"
    "응답 형식:\n"
    "1. 요약 2~3 문장.\n"
    "2. 발견 사항 최대 3건 (없으면 '특이사항 없음').\n"
    "3. 본문 산문에 이 저장소의 도메인 영역 키워드를 평문으로 노출하지 마세요. "
    "GitHub URL 내부 슬러그는 예외입니다.\n"
    "4. 응답에 git push --force / git reset --hard 같은 위험 명령을 권장하지 않습니다."
)


# write 도구 — patch 생성 시스템 프롬프트.
WRITE_PATCH_SYSTEM_PROMPT: str = (
    "당신은 사용자(이하영)의 코드 패치 생성 비서입니다. PR 컨텍스트와 요청을 받아 "
    "unified diff 형식의 패치 1개를 생성합니다.\n\n"
    "규칙:\n"
    "- 응답은 unified diff (`--- a/...`, `+++ b/...`) 형식만 포함합니다.\n"
    "- 변경 범위는 요청에 명시된 파일·라인에 한정합니다.\n"
    "- `.env`, `.git/`, `secrets/`, `.key`, `.pem`, `credentials` 경로는 절대 수정하지 않습니다.\n"
    "- `rm -rf`, `> /dev/`, force push, reset --hard 같은 위험 표지를 본문에 포함하지 않습니다.\n"
    "- 본문 산문에 도메인 영역 키워드를 평문으로 노출하지 않습니다."
)


# write 도구 — 커밋 메시지 생성 시스템 프롬프트.
WRITE_COMMIT_MSG_SYSTEM_PROMPT: str = (
    "당신은 사용자(이하영)의 커밋 메시지 작성 비서입니다. staged 변경사항 요약을 "
    "받아 한글 1줄 커밋 메시지를 작성합니다.\n\n"
    "규칙:\n"
    "- 한글 1줄 (50자 이내 권장).\n"
    "- '추가/수정/제거/리팩토링' 같은 명확한 동사로 시작.\n"
    "- 본문에 도메인 영역 키워드를 평문으로 노출하지 않습니다.\n"
    "- `--amend`, `--no-verify` 같은 플래그는 절대 메시지에 포함하지 않습니다.\n"
    "- 응답은 커밋 메시지 본문만 포함 (코드 블록·인용 부호 없이)."
)


def is_sdk_available() -> bool:
    """SDK import 가능 여부.

    구독 모드 / API 키 모드 판별은 SDK 가 내부에서 한다. 본 함수는 라이브러리
    설치 + 환경 변수 1단계 검증만.
    """
    try:
        import claude_agent_sdk  # noqa: F401
    except ImportError:
        return False
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if api_key and not api_key.startswith("sk-ant-"):
        # 잘못된 prefix 인 경우 데몬 시작 차단은 config 단계의 책임 —
        # 본 함수는 단순 boolean.
        return False
    return True


def make_reviewer_callable(
    *,
    cwd: str | None = None,
) -> Callable[[int], ReviewResult] | None:
    """reviewer SDK callable 생성.

    PRD §3.1 — `nl_sdk_runtime` 패턴 재사용. PR 번호를 받아 SDK 호출 →
    `ReviewResult` 반환.

    SDK import 실패 시 None 반환 — 호출 측이 reviewer 비활성으로 처리.
    """
    try:
        from claude_agent_sdk import (
            AssistantMessage,
            ClaudeAgentOptions,
            TextBlock,
            query,
        )
    except ImportError as exc:
        _LOGGER.warning(
            "reviewer SDK import 실패 (%s) — reviewer 비활성", type(exc).__name__
        )
        return None

    def _review(pr_number: int) -> ReviewResult:
        """PR 번호를 입력받아 SDK 신규 세션으로 리뷰 호출."""
        # SDK 호출 prompt — 리뷰 instruction + PR 번호.
        # SDK builtin Bash 도구가 `gh pr diff <N>` 으로 PR diff 를 가져온다는 가정.
        # PR 번호 외 본문 컨텍스트는 SDK 가 도구 호출로 수집.
        user_prompt = (
            f"PR #{pr_number} 의 변경사항을 검토해 주세요. "
            f"`gh pr diff {pr_number}` 로 diff 를 확인하고, "
            f"본 시스템 프롬프트의 형식에 맞춰 한국어로 보고해 주세요."
        )
        options = ClaudeAgentOptions(
            model=MODEL_SONNET_ID,
            system_prompt=REVIEWER_SYSTEM_PROMPT,
            # reviewer 는 read-only 도구만 — write 도구는 reviewer 의 책임이 아니다.
            allowed_tools=["Read", "Glob", "Grep", "Bash"],
            disallowed_tools=["Edit", "Write", "NotebookEdit"],
            max_turns=10,
            cwd=cwd,
        )
        chunks: list[str] = []

        async def _drain() -> None:
            async for message in query(prompt=user_prompt, options=options):
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            chunks.append(block.text)

        import asyncio

        asyncio.run(_drain())
        raw = "".join(chunks).strip()
        return _parse_review_response(raw)

    return _review


def _parse_review_response(raw: str) -> ReviewResult:
    """SDK raw 응답을 `ReviewResult` 로 파싱.

    예상 형식:
    - 첫 2~3 문장은 요약.
    - 그 뒤 `발견 사항` 섹션에 bullet (`-` 시작).
    - 빈 경우 "특이사항 없음" 으로 기본값.
    """
    if not raw:
        return ReviewResult(
            summary="응답 본문이 비어 있어요.",
            findings=[],
            detail="",
        )

    lines = raw.splitlines()
    summary_lines: list[str] = []
    findings: list[str] = []

    in_findings = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        lowered = stripped.lower()
        if "발견" in stripped or lowered.startswith("findings"):
            in_findings = True
            continue
        if in_findings:
            if stripped.startswith("-") or stripped.startswith("*"):
                findings.append(stripped.lstrip("-* ").strip())
            # 그 외 라인은 무시.
        else:
            summary_lines.append(stripped)

    summary = " ".join(summary_lines[:3]).strip() or "리뷰 결과를 정리했습니다."
    if not findings:
        findings = []

    return ReviewResult(
        summary=summary,
        findings=findings,
        detail=raw,
    )


def make_patch_generator(
    *,
    cwd: str | None = None,
) -> Callable[[int, str], str] | None:
    """patch 생성 SDK callable 생성.

    인자: (pr_number, user_request_text) → unified diff 텍스트.
    """
    try:
        from claude_agent_sdk import (
            AssistantMessage,
            ClaudeAgentOptions,
            TextBlock,
            query,
        )
    except ImportError as exc:
        _LOGGER.warning(
            "patch generator SDK import 실패 (%s) — write 도구 비활성",
            type(exc).__name__,
        )
        return None

    def _generate(pr_number: int, user_request: str) -> str:
        user_prompt = (
            f"PR #{pr_number} 컨텍스트에서 다음 요청을 수행하는 "
            f"unified diff 패치를 생성해 주세요.\n\n"
            f"요청: {user_request}\n\n"
            f"`gh pr diff {pr_number}` 와 관련 파일 `Read` 로 컨텍스트를 확인한 뒤, "
            f"unified diff 형식만 응답으로 출력하세요."
        )
        options = ClaudeAgentOptions(
            model=MODEL_SONNET_ID,
            system_prompt=WRITE_PATCH_SYSTEM_PROMPT,
            allowed_tools=["Read", "Glob", "Grep", "Bash"],
            disallowed_tools=["Edit", "Write", "NotebookEdit"],
            max_turns=10,
            cwd=cwd,
        )
        chunks: list[str] = []

        async def _drain() -> None:
            async for message in query(prompt=user_prompt, options=options):
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            chunks.append(block.text)

        import asyncio

        asyncio.run(_drain())
        raw = "".join(chunks).strip()
        return _extract_unified_diff(raw)

    return _generate


def _extract_unified_diff(raw: str) -> str:
    """SDK 응답에서 unified diff 블록만 추출.

    응답이 ```diff ... ``` 코드펜스를 포함하면 그 내부만 가져오고,
    아니면 raw 그대로 반환.
    """
    if not raw:
        return ""
    # 코드펜스 안의 첫 diff 블록만 추출.
    import re

    fence_match = re.search(
        r"```(?:diff|patch)?\s*\n(.*?)\n```",
        raw,
        re.DOTALL,
    )
    if fence_match:
        return fence_match.group(1).strip() + "\n"
    return raw.strip() + "\n"


def make_write_converter(
    *,
    cwd: str | None = None,
    timeout_seconds: float = WRITE_CONVERTER_TIMEOUT_SECONDS,
) -> Callable[[str, str], str] | None:
    """NL → structured 변환 SDK callable 생성 (PRD `dev-relay-write-tools-nl.md` §3.2).

    인자 시그니처: (system_prompt, user_text) → JSON 문자열.

    PM 결정 §10 — Sonnet 4.6 사용 (변환 정확도 우선). 시스템 프롬프트가 strict
    JSON 출력만 허용하도록 강제하고, 본 callable 은 raw 응답을 그대로 반환한다.
    JSON 파싱·검증은 `write_classifier.parse_conversion_response` 가 처리.

    SDK import 실패 시 None 반환 — 호출 측이 변환 분기 비활성으로 graceful degradation.

    PR #59 reviewer P1-3 후속 — `timeout_seconds` 가 SDK 호출 상한. 초과 시
    `WriteConverterTimeout` raise. `_handle_nl_write_conversion` 이 NL 분기
    `_nl_turn_lock` 보유 상태에서 동기 호출하므로, hang 시 NL 분기 영구 차단
    가능성을 0 으로 만든다. default = `WRITE_CONVERTER_TIMEOUT_SECONDS`.
    """
    try:
        from claude_agent_sdk import (
            AssistantMessage,
            ClaudeAgentOptions,
            TextBlock,
            query,
        )
    except ImportError as exc:
        _LOGGER.warning(
            "write converter SDK import 실패 (%s) — NL 자율 트리거 비활성",
            type(exc).__name__,
        )
        return None

    def _convert(system_prompt: str, user_text: str) -> str:
        options = ClaudeAgentOptions(
            model=MODEL_SONNET_ID,
            system_prompt=system_prompt,
            # 변환은 도구 호출 불필요 — strict JSON 합성만.
            allowed_tools=[],
            max_turns=1,
            cwd=cwd,
        )
        chunks: list[str] = []

        async def _drain() -> None:
            async for message in query(prompt=user_text, options=options):
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            chunks.append(block.text)

        import asyncio

        # PR #59 reviewer P1-3 — `asyncio.wait_for` 로 SDK hang 시 NL 분기
        # 영구 차단 방지. timeout 초과 시 명시 `WriteConverterTimeout` raise →
        # 호출 측 (`write_classifier.convert`) 이 reason="timeout" 으로 매핑.
        async def _drain_with_timeout() -> None:
            await asyncio.wait_for(_drain(), timeout=timeout_seconds)

        try:
            asyncio.run(_drain_with_timeout())
        except (asyncio.TimeoutError, TimeoutError) as exc:
            _LOGGER.warning(
                "write converter timeout (%.1fs) — NL 분기 락 release 보장",
                timeout_seconds,
            )
            raise WriteConverterTimeout(
                f"write converter timeout after {timeout_seconds}s"
            ) from exc
        return "".join(chunks).strip()

    return _convert


def make_commit_message_generator(
    *,
    cwd: str | None = None,
) -> Callable[[str], str] | None:
    """커밋 메시지 생성 SDK callable 생성.

    인자: staged diff 요약 텍스트 → 한글 1줄 메시지.
    """
    try:
        from claude_agent_sdk import (
            AssistantMessage,
            ClaudeAgentOptions,
            TextBlock,
            query,
        )
    except ImportError as exc:
        _LOGGER.warning(
            "commit msg generator SDK import 실패 (%s)", type(exc).__name__
        )
        return None

    def _generate(staged_summary: str) -> str:
        user_prompt = (
            "다음 staged 변경사항을 요약한 한글 1줄 커밋 메시지를 작성해 주세요.\n\n"
            f"{staged_summary}"
        )
        options = ClaudeAgentOptions(
            model=MODEL_HAIKU_ID,
            system_prompt=WRITE_COMMIT_MSG_SYSTEM_PROMPT,
            allowed_tools=[],
            max_turns=1,
            cwd=cwd,
        )
        chunks: list[str] = []

        async def _drain() -> None:
            async for message in query(prompt=user_prompt, options=options):
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            chunks.append(block.text)

        import asyncio

        asyncio.run(_drain())
        msg = "".join(chunks).strip()
        # 1줄로 강제 — 줄바꿈이 있으면 첫 줄만.
        first_line = msg.splitlines()[0].strip() if msg else ""
        return first_line

    return _generate


__all__ = [
    "MODEL_HAIKU_ID",
    "MODEL_SONNET_ID",
    "REVIEWER_SYSTEM_PROMPT",
    "WRITE_COMMIT_MSG_SYSTEM_PROMPT",
    "WRITE_CONVERTER_TIMEOUT_SECONDS",
    "WRITE_PATCH_SYSTEM_PROMPT",
    "WriteConverterTimeout",
    "is_sdk_available",
    "make_commit_message_generator",
    "make_patch_generator",
    "make_reviewer_callable",
    "make_write_converter",
]
