"""
실패 분류 매핑 (Dev Manager — agent integration).

PRD `dev-relay-agent-integration.md` §3.5: reviewer / merge 호출 실패는 다음
5개 분류 중 하나로 매핑되어야 한다 — 그 외는 `unknown_error` fallback.

| 분류                        | 트리거                                       |
|-----------------------------|---------------------------------------------|
| `destructive_blocked`       | `assert_no_destructive_intent` raise        |
| `sdk_timeout`               | SDK 호출이 watchdog timeout 초과            |
| `github_unauthorized`       | `gh` / API 401·403                          |
| `github_unprocessable`      | `gh` / API 422 (mergeable=false 등)         |
| `compliance_blocked`        | `slack_renderer` 가드가 발사 차단            |

본 모듈은 외부 라이브러리 의존이 없는 순수 매핑 로직만 담는다 — 테스트 가능성
극대화. 분류 결과는 `(classification, user_message)` 튜플 — 사용자 노출
메시지는 `slack_renderer` 의 정적 템플릿을 그대로 인용한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ai.dev_relay.slack_renderer import (
    TEMPLATE_FAIL_COMPLIANCE_BLOCKED,
    TEMPLATE_FAIL_DESTRUCTIVE_BLOCKED,
    TEMPLATE_FAIL_GITHUB_UNAUTHORIZED,
    TEMPLATE_FAIL_GITHUB_UNPROCESSABLE,
    TEMPLATE_FAIL_SDK_TIMEOUT,
    TEMPLATE_FAIL_UNKNOWN,
)


class FailureClassification(str, Enum):
    """PRD §3.5 5개 분류 + fallback."""

    DESTRUCTIVE_BLOCKED = "destructive_blocked"
    SDK_TIMEOUT = "sdk_timeout"
    GITHUB_UNAUTHORIZED = "github_unauthorized"
    GITHUB_UNPROCESSABLE = "github_unprocessable"
    COMPLIANCE_BLOCKED = "compliance_blocked"
    UNKNOWN_ERROR = "unknown_error"


@dataclass(frozen=True, slots=True)
class FailureReport:
    """분류 + 사용자 노출 메시지 + 내부 사유 1라인 (audit 용)."""

    classification: FailureClassification
    user_message: str
    detail: str  # audit / 로그용. Slack 발사 금지 (raw stderr 가능).


# 분류별 사용자 노출 메시지 매핑 (single source).
_USER_MESSAGES: dict[FailureClassification, str] = {
    FailureClassification.DESTRUCTIVE_BLOCKED: TEMPLATE_FAIL_DESTRUCTIVE_BLOCKED,
    FailureClassification.SDK_TIMEOUT: TEMPLATE_FAIL_SDK_TIMEOUT,
    FailureClassification.GITHUB_UNAUTHORIZED: TEMPLATE_FAIL_GITHUB_UNAUTHORIZED,
    FailureClassification.GITHUB_UNPROCESSABLE: TEMPLATE_FAIL_GITHUB_UNPROCESSABLE,
    FailureClassification.COMPLIANCE_BLOCKED: TEMPLATE_FAIL_COMPLIANCE_BLOCKED,
    FailureClassification.UNKNOWN_ERROR: TEMPLATE_FAIL_UNKNOWN,
}


def user_message_for(classification: FailureClassification) -> str:
    """분류 → 정적 템플릿 메시지. fallback 보장."""
    return _USER_MESSAGES.get(classification, TEMPLATE_FAIL_UNKNOWN)


# `gh` / GitHub HTTP 코드 → 분류 매핑.
def classify_github_status(status_code: int) -> FailureClassification:
    if status_code in (401, 403):
        return FailureClassification.GITHUB_UNAUTHORIZED
    if status_code == 422:
        return FailureClassification.GITHUB_UNPROCESSABLE
    return FailureClassification.UNKNOWN_ERROR


def classify_exception(
    exc: BaseException,
    *,
    timeout_marker_types: tuple[type[BaseException], ...] = (TimeoutError,),
) -> FailureClassification:
    """일반 예외를 분류 한 글자로 변환.

    호출 측이 GitHub HTTP 코드를 알 수 있는 경우는 `classify_github_status` 를
    우선 사용하고, 본 함수는 SDK 호출 / dispatcher 가드 / 컴플라이언스 가드의
    raise 를 분류하는 데 쓴다.

    `timeout_marker_types` 는 호출 측이 자체 timeout 예외 클래스를 추가로
    매핑하고 싶을 때 주입한다.
    """
    # 직접 import 가 dependency cycle 을 만들지 않도록 lazy 검사.
    from ai.dev_relay.agent_runner import DestructiveOperationBlocked

    if isinstance(exc, DestructiveOperationBlocked):
        return FailureClassification.DESTRUCTIVE_BLOCKED
    if isinstance(exc, timeout_marker_types):
        return FailureClassification.SDK_TIMEOUT
    return FailureClassification.UNKNOWN_ERROR


def report(
    classification: FailureClassification, *, detail: str = ""
) -> FailureReport:
    """분류 + 사용자 메시지 + 내부 사유를 묶은 단일 객체."""
    return FailureReport(
        classification=classification,
        user_message=user_message_for(classification),
        detail=detail or classification.value,
    )


__all__ = [
    "FailureClassification",
    "FailureReport",
    "classify_exception",
    "classify_github_status",
    "report",
    "user_message_for",
]
