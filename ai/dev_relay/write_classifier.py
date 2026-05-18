"""
NL → structured 변환기 (Dev Manager Phase 3).

PRD: docs/prd/dev-relay-write-tools-nl.md §3.2

설계
- `WRITE_REQUEST` 라벨이 떨어진 NL 입력을 Sonnet 변환 SDK 호출로 structured
  명령 JSON 으로 변환한다.
- 본 모듈은 *순수* 변환·검증 로직만 제공. SDK 실호출은 호출 측이 callable 로
  주입한다 (테스트 가능성 + SDK 미설정 환경 호환).
- 변환 결과 JSON 형식 위반 / 필드 누락 / 화이트리스트 밖 tool / 낮은 confidence
  는 `ConversionRejection` 으로 분류해 호출 측이 §3.4 모호 의도 거절 흐름을
  태운다.

변환 결과 흐름
1. 변환 SDK 호출 → strict JSON 문자열.
2. JSON 파싱 → 필수 필드 검증 (`tool`, `pr`, `confidence`).
3. `tool` 값이 화이트리스트 (apply_patch / commit / push) 안인지.
4. `confidence` 가 threshold (default 0.7) 이상인지.
5. 통과 시 `ConversionSuccess` 반환 — `structured_command` 가 dispatcher 정규식
   매치 가능한 문자열 (예: `apply patch pr=32`).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Callable


# PRD `dev-relay-write-tools-nl.md` §3.4 — 모호 거절 confidence threshold 기본값.
# 1~2주 모니터링 후 조정 (PM 결정사항 §10).
DEFAULT_CONFIDENCE_THRESHOLD: float = 0.7


# 변환이 합성할 수 있는 도구 화이트리스트. Phase 2 의 3종 그대로
# (`dev-relay-write-tools.md` §3.2.3). 신규 도구 도입 시 본 셋 확장.
_ALLOWED_TOOLS: frozenset[str] = frozenset(
    {"apply_patch", "commit", "push"}
)


# tool 값 → dispatcher 정규식 매치 문자열 매핑 (`dispatcher.parse` 의 normalized
# 결과와 동일 형식). PR 번호는 placeholder 로 합성.
_TOOL_TO_COMMAND_TEMPLATE: dict[str, str] = {
    "apply_patch": "apply patch pr={pr}",
    "commit": "commit pr={pr}",
    "push": "push pr={pr}",
}


class ConversionFailReason(str, Enum):
    """변환 실패 분류 (audit 의 `reason` 필드로 그대로 기록)."""

    PARSE_ERROR = "parse_error"
    MISSING_FIELD = "missing_field"
    UNKNOWN_TOOL = "unknown_tool"
    LOW_CONFIDENCE = "low_confidence"
    INVALID_PR = "invalid_pr"


@dataclass(frozen=True, slots=True)
class ConversionSuccess:
    """변환 성공 결과 — 호출 측이 Phase 2 흐름에 그대로 재진입."""

    tool: str
    pr_number: int
    confidence: float
    structured_command: str  # dispatcher 정규식 매치 가능 (예: "apply patch pr=32")
    prompt_tokens: int = 0
    response_tokens: int = 0


@dataclass(frozen=True, slots=True)
class ConversionRejection:
    """변환 실패 결과 — 호출 측이 §3.4 모호 의도 거절 흐름."""

    reason: ConversionFailReason
    prompt_tokens: int = 0
    response_tokens: int = 0


# 변환 SDK callable 시그니처 — (system_prompt, user_text) → JSON 문자열.
# 외부에서 SDK 호출을 주입. 테스트는 mock callable 로 대체.
WriteConverterCallable = Callable[[str, str], str]


# 변환 SDK 시스템 프롬프트 — strict JSON 출력만 허용.
# 외부 노출되지 않으므로 영어 (LLM 시스템 프롬프트 한정). 도메인 키워드 0 hit.
WRITE_CONVERT_SYSTEM_PROMPT: str = (
    "You convert a user's natural language request into a strict JSON object "
    "describing a single safe developer action.\n\n"
    "Rules:\n"
    "- Output exactly one JSON object. No prose, no code fences, no extra text.\n"
    "- Required fields: `tool` (string), `pr` (integer), `confidence` (float 0..1).\n"
    "- `tool` must be one of: `apply_patch`, `commit`, `push`.\n"
    "- `pr` must be the GitHub PR number the user is targeting (positive integer).\n"
    "- `confidence` reflects how certain you are about the user's intent and target PR.\n"
    "- If the user requests destructive ops (force push, rebase, reset --hard, "
    "branch delete, .env edits), set `confidence` to 0.0 and `tool` to "
    "`apply_patch` so the caller rejects via lower-layer guards.\n"
    "- If the user requests multiple chained actions, convert only the first action.\n"
    "- If you cannot identify a clear PR number, set `confidence` below 0.5.\n"
    "- Do not include any extra fields. Do not add explanations.\n\n"
    "Example output:\n"
    '{"tool": "apply_patch", "pr": 32, "confidence": 0.9}'
)


# 변환 결과 JSON 추출 — SDK 가 가끔 코드 펜스로 감싸는 경우 대비.
_JSON_FENCE_RE: re.Pattern[str] = re.compile(
    r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL
)


def _extract_json_object(raw: str) -> str:
    """raw 응답에서 JSON object 본문만 추출.

    1. 코드 펜스 안의 첫 JSON object.
    2. 본문에서 첫 `{` ~ 마지막 `}` 까지.
    3. fallback — raw 그대로.
    """
    if not raw:
        return ""
    fence_match = _JSON_FENCE_RE.search(raw)
    if fence_match:
        return fence_match.group(1).strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        return raw[start : end + 1].strip()
    return raw.strip()


def parse_conversion_response(
    raw: str,
    *,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
) -> ConversionSuccess | ConversionRejection:
    """변환 SDK raw 응답을 검증 후 success/rejection 으로 분류.

    PRD `dev-relay-write-tools-nl.md` §3.2.1 단계 2~3 + §3.4 거절 조건.

    검증 순서 (실패 시 그 자리에서 reject):
    1. JSON 파싱.
    2. 필수 필드 (`tool`, `pr`, `confidence`) 존재.
    3. `tool` 값이 화이트리스트.
    4. `pr` 가 양의 정수.
    5. `confidence` 가 threshold 이상.
    """
    body = _extract_json_object(raw)
    if not body:
        return ConversionRejection(reason=ConversionFailReason.PARSE_ERROR)
    try:
        data = json.loads(body)
    except (ValueError, TypeError):
        return ConversionRejection(reason=ConversionFailReason.PARSE_ERROR)
    if not isinstance(data, dict):
        return ConversionRejection(reason=ConversionFailReason.PARSE_ERROR)

    tool = data.get("tool")
    pr = data.get("pr")
    confidence = data.get("confidence")

    if tool is None or pr is None or confidence is None:
        return ConversionRejection(reason=ConversionFailReason.MISSING_FIELD)

    if not isinstance(tool, str) or tool not in _ALLOWED_TOOLS:
        return ConversionRejection(reason=ConversionFailReason.UNKNOWN_TOOL)

    # bool 은 int 의 서브타입 — 명시적으로 거절.
    if isinstance(pr, bool) or not isinstance(pr, int) or pr <= 0:
        return ConversionRejection(reason=ConversionFailReason.INVALID_PR)

    try:
        conf_value = float(confidence)
    except (TypeError, ValueError):
        return ConversionRejection(reason=ConversionFailReason.MISSING_FIELD)

    if conf_value < confidence_threshold:
        return ConversionRejection(reason=ConversionFailReason.LOW_CONFIDENCE)

    template = _TOOL_TO_COMMAND_TEMPLATE.get(tool)
    if template is None:
        # 방어 코드 — 화이트리스트 통과했는데 매핑 누락 (도구 추가 시 잊은 케이스).
        return ConversionRejection(reason=ConversionFailReason.UNKNOWN_TOOL)

    return ConversionSuccess(
        tool=tool,
        pr_number=pr,
        confidence=conf_value,
        structured_command=template.format(pr=pr),
    )


def convert(
    user_text: str,
    *,
    converter: WriteConverterCallable,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
) -> ConversionSuccess | ConversionRejection:
    """사용자 NL 텍스트를 structured 명령으로 변환.

    `converter` callable 이 SDK 호출 (또는 mock) 을 수행한다. 본 함수는 시스템
    프롬프트 주입 + 응답 검증만 책임진다.

    빈 입력은 LLM 호출 없이 즉시 `PARSE_ERROR` 로 거절.
    """
    if not user_text or not user_text.strip():
        return ConversionRejection(reason=ConversionFailReason.PARSE_ERROR)
    try:
        raw = converter(WRITE_CONVERT_SYSTEM_PROMPT, user_text)
    except Exception:  # noqa: BLE001
        # SDK 호출 실패 — parse_error 로 분류해 호출 측이 §3.4 흐름으로 태운다.
        return ConversionRejection(reason=ConversionFailReason.PARSE_ERROR)
    return parse_conversion_response(
        raw, confidence_threshold=confidence_threshold
    )


__all__ = [
    "DEFAULT_CONFIDENCE_THRESHOLD",
    "WRITE_CONVERT_SYSTEM_PROMPT",
    "ConversionFailReason",
    "ConversionRejection",
    "ConversionSuccess",
    "WriteConverterCallable",
    "convert",
    "parse_conversion_response",
]
