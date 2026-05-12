"""
devops 머지 호출 (Dev Manager — agent integration).

PRD `dev-relay-agent-integration.md` §3.3:
- `_perform_merge` 는 `[승인]` 버튼 핸들러에서만 호출되는 격리된 entry point.
- `AgentRunner` 우회 — 머지는 SDK 출력 텍스트에 의존하지 않는 결정형 op 라
  destructive 가드의 적용 대상이 아니다 (오히려 머지가 의도적 destructive 임).
- 머지 전략: `gh pr merge <N> --squash --delete-branch` 고정 (PRD §10).

본 모듈은 외부 프로세스 호출(`gh`) 자체는 caller-injected callable 로 위임한다
— 테스트에서 mock 으로 대체 가능. 실 호출은 `main._build_merge_runner` 가
`subprocess.run` 으로 wrap 한다.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Callable

from ai.dev_relay.failures import FailureClassification

_LOGGER = logging.getLogger("ai.dev_relay.merger")

MERGE_STRATEGY: str = "squash"


@dataclass(frozen=True, slots=True)
class MergeOutcome:
    """머지 호출 결과."""

    success: bool
    sha: str | None
    detail: str  # 성공 시 보조 정보, 실패 시 분류용 raw stderr.
    classification: FailureClassification | None = None


# `_perform_merge` 가 호출하는 외부 작업자. PR 번호를 받아 MergeOutcome 반환.
MergeWorker = Callable[[int], MergeOutcome]


@dataclass(frozen=True, slots=True)
class ApprovalContext:
    """`[승인]` 버튼 페이로드 + 핸들러 환경 검증 결과."""

    pr_number: int
    idempotency_key: str
    job_id: int
    user_id: str  # 클릭한 사용자 (화이트리스트 통과한 경우만).


class MergeRejection(RuntimeError):
    """머지 호출 전 사전 검증 실패. `_perform_merge` 호출 자체가 차단됐음을 의미."""


# PRD §3.3 추가 안전망 — `MergeRejection` 의 reason 코드. 호출 측이 사용자 안내
# 메시지를 분기하기 위해 비교한다 (문자열 비교로 충분 — 본 모듈 외부 의존 0).
REJECTION_REASON_RESTART_NO_EXPECTED: str = "expected approval missing (restart)"


def validate_approval(
    *,
    pr_number_in_payload: int | None,
    idempotency_key_in_payload: str | None,
    job_id_in_payload: int | None,
    expected_idempotency_key: str | None,
    expected_job_id: int | None,
    user_id: str,
    allowed_user_ids: frozenset[str],
    action_id: str,
) -> ApprovalContext:
    """`[승인]` 버튼 페이로드의 사전 검증 (PRD §3.3 추가 안전망).

    실패 시 `MergeRejection` raise — 호출 측은 이 예외를 잡아 사용자 안내 +
    audit 기록을 수행한다.

    PR #43 reviewer P2-1 후속: `expected_*` 가 모두 None 인 경우 (데몬 재시작
    후 이전 세션의 메시지 버튼이 눌린 케이스) 페이로드 자체만 검증하던 약화된
    fallback 분기를 제거한다. 이전 세션 페이로드는 idempotency_key 매칭 backstop
    을 통과시킬 수 없으므로 즉시 거절한다.
    """
    if action_id != "approve_merge":
        raise MergeRejection(f"unexpected action_id={action_id}")
    if user_id not in allowed_user_ids:
        raise MergeRejection("user_id not in allowed list")
    if pr_number_in_payload is None or pr_number_in_payload <= 0:
        raise MergeRejection("invalid pr_number in payload")
    if not idempotency_key_in_payload:
        raise MergeRejection("missing idempotency_key in payload")
    if job_id_in_payload is None or job_id_in_payload <= 0:
        raise MergeRejection("invalid job_id in payload")
    # PR #43 reviewer P2-1: expected_* 둘 중 하나라도 None 이면 즉시 거절.
    # 단일 정의 지점 — 호출 측 회귀 0 보장.
    if expected_idempotency_key is None or expected_job_id is None:
        raise MergeRejection(REJECTION_REASON_RESTART_NO_EXPECTED)
    if expected_idempotency_key != idempotency_key_in_payload:
        raise MergeRejection("idempotency_key mismatch")
    if expected_job_id != job_id_in_payload:
        raise MergeRejection("job_id mismatch")
    return ApprovalContext(
        pr_number=pr_number_in_payload,
        idempotency_key=idempotency_key_in_payload,
        job_id=job_id_in_payload,
        user_id=user_id,
    )


# `gh pr merge` 실패 분류 보조: stderr 에서 분류 단서를 추출.
_AUTH_PATTERNS: tuple[str, ...] = (
    "401",
    "403",
    "unauthorized",
    "forbidden",
    "permission",
    "authentication",
)
_UNPROCESSABLE_PATTERNS: tuple[str, ...] = (
    "422",
    "unprocessable",
    "mergeable",
    "conflict",
    "checks_failed",
    "checks failed",
)


def classify_merge_stderr(stderr: str | None) -> FailureClassification:
    """`gh` stderr 텍스트를 보고 분류를 추정.

    raw stderr 는 사용자에게 노출되지 않는다 — `slack_renderer` 의 정적 템플릿이
    노출되며 raw 는 audit / 로그 전용.
    """
    if not stderr:
        return FailureClassification.UNKNOWN_ERROR
    needle = stderr.lower()
    for pattern in _AUTH_PATTERNS:
        if pattern in needle:
            return FailureClassification.GITHUB_UNAUTHORIZED
    for pattern in _UNPROCESSABLE_PATTERNS:
        if pattern in needle:
            return FailureClassification.GITHUB_UNPROCESSABLE
    return FailureClassification.UNKNOWN_ERROR


_SHA_RE = re.compile(r"\b[0-9a-f]{7,40}\b")


def extract_sha(stdout: str | None) -> str | None:
    """`gh pr merge` 성공 시 stdout/stderr 에서 SHA 추출 (best-effort).

    정확히 추출되지 않아도 머지 성공 자체는 invocation 의 returncode 로 판정 —
    SHA 가 None 이어도 사용자 메시지는 발사된다.
    """
    if not stdout:
        return None
    match = _SHA_RE.search(stdout)
    return match.group(0) if match else None


def perform_merge(
    *,
    approval: ApprovalContext,
    worker: MergeWorker,
) -> MergeOutcome:
    """검증된 approval context 에 대해 머지를 실행.

    호출 측은 본 함수 호출 전에 반드시 `validate_approval` 을 통과시켜야 한다.
    `_perform_merge` 라는 이름은 `main` 의 wrapper 가 그대로 사용 — 본 모듈은
    순수 로직만 담는다.
    """
    _LOGGER.info(
        "merge invoke: pr=%d job_id=%d strategy=%s",
        approval.pr_number,
        approval.job_id,
        MERGE_STRATEGY,
    )
    return worker(approval.pr_number)


__all__ = [
    "ApprovalContext",
    "MERGE_STRATEGY",
    "MergeOutcome",
    "MergeRejection",
    "MergeWorker",
    "REJECTION_REASON_RESTART_NO_EXPECTED",
    "classify_merge_stderr",
    "extract_sha",
    "perform_merge",
    "validate_approval",
]
