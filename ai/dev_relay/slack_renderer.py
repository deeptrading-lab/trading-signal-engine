"""
Block Kit 메시지 빌더 + 발사 직전 컴플라이언스 가드 (Dev Manager).

PRD §3.5 / §3.7 / AC-16:
- 외부 노출 텍스트(메시지 본문·버튼 라벨·앱 표시)는 모두 본 모듈을 거친다.
- 발사 직전 `assert_no_forbidden` 으로 도메인 키워드를 차단 (`ai.coordinator._compliance`
  단일 정의 지점 재사용).
- Block Kit 액션 페이로드의 `value` 에는 `idempotency_key:job_id` 를 묶어 replay
  방지 (PRD §3.5).

본 모듈은 Slack SDK 에 직접 의존하지 않으며, 빌드된 dict 만 반환한다 — slack-bolt
호출은 호출 측(`main`)이 담당한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ai.coordinator._compliance import assert_no_forbidden, find_forbidden_keywords
from ai.dev_relay._url_escape import restore_urls, with_urls_escaped

# 발사 차단 시 사용자에게 보낼 fallback 메시지. 자기 자신은 정책 통과 대상.
FALLBACK_RESPONSE: str = "응답 생성 중 오류가 발생했어요. 다시 시도해 주세요."

# 큐 적재 안내 (AC-3, AC-14).
TEMPLATE_QUEUE_ACCEPTED_REVIEW: str = "PR #{pr_number} 리뷰를 시작합니다. 진행 상황은 이 스레드에 보고할게요."
TEMPLATE_QUEUE_ACCEPTED_MERGE: str = "PR #{pr_number} 머지 요청을 받았습니다. 아래 버튼으로 승인해 주세요."
TEMPLATE_QUEUE_BUSY: str = "현재 1건 처리 중입니다. 큐에 적재됐어요 (대기 {pending}건)."

# 재시작 복구 안내 (PRD §3.4).
TEMPLATE_RECOVERY_NOTICE: str = (
    "이전 세션이 끊겨 작업이 중단됐어요. 다시 명령해 주세요."
)

# 취소 안내 (AC-6).
TEMPLATE_CANCEL_NOTICE: str = "취소했습니다. 이유를 알려주시면 다음에 반영할게요."

# rate limit 안내 (AC-15).
TEMPLATE_RATE_LIMIT: str = "잠시 후 다시 시도해 주세요."

# unknown / destructive fallback.
TEMPLATE_UNKNOWN_COMMAND: str = (
    "사용 가능한 명령은 다음과 같아요.\n"
    "- status — 현재 큐 현황 요약\n"
    "- review pr <번호> — PR 리뷰 요청\n"
    "- merge pr <번호> — PR 머지 (2단계 승인)"
)
TEMPLATE_DESTRUCTIVE_BLOCKED: str = (
    "이 작업은 PC에 직접 들어가서 수행해 주세요. 봇은 위험 명령을 실행하지 않습니다."
)

# PRD `dev-relay-agent-integration.md` §3.1 — 머지 carve-out 안내.
TEMPLATE_MERGE_CARVE_OUT_NOTICE: str = (
    "이전 세션에서 진행되던 머지 1건의 결과를 확인하지 못했습니다. "
    "PR #{pr_number} 을 직접 확인해 주세요."
)

# PRD `dev-relay-agent-integration.md` §3.2 — [상세 보기] 캐시 유실 안내.
TEMPLATE_REVIEW_DETAIL_LOOKUP_FAILED: str = (
    "원본 결과를 더 이상 표시할 수 없습니다. 다시 `review pr <N>` 을 실행해 주세요."
)

# PRD `dev-relay-agent-integration.md` §3.5 — 실패 분류 → 사용자 노출 메시지.
TEMPLATE_FAIL_DESTRUCTIVE_BLOCKED: str = (
    "이 작업은 PC에서 직접 처리해 주세요."
)
TEMPLATE_FAIL_SDK_TIMEOUT: str = (
    "응답이 지연되어 작업을 중단했어요. 다시 시도해 주세요."
)
TEMPLATE_FAIL_GITHUB_UNAUTHORIZED: str = (
    "PR 접근 권한이 없습니다. 토큰 권한을 확인해 주세요."
)
TEMPLATE_FAIL_GITHUB_UNPROCESSABLE: str = (
    "머지 조건을 충족하지 못했습니다 (예: 충돌·체크 실패)."
)
TEMPLATE_FAIL_COMPLIANCE_BLOCKED: str = (
    "응답 생성 중 오류가 발생했어요. 다시 시도해 주세요."
)
TEMPLATE_FAIL_UNKNOWN: str = (
    "알 수 없는 오류로 작업을 마치지 못했어요. 잠시 후 다시 시도해 주세요."
)


# ---------------------------------------------------------------------------
# 발사 직전 가드 — 모든 외부 텍스트는 본 함수를 거친다.
# ---------------------------------------------------------------------------


def guard_text(text: str | None) -> str:
    """텍스트에 도메인 키워드가 있으면 fallback 으로 치환.

    `assert_no_forbidden` 은 테스트용 strict 검사, 본 함수는 runtime 가드.
    매치 시 원본을 발사하지 않고 안전한 fallback 으로 대체한다.
    """
    if not text:
        return text or ""
    if find_forbidden_keywords(text):
        return FALLBACK_RESPONSE
    return text


def guard_text_with_urls(text: str | None) -> str:
    """URL 부분을 placeholder 로 escape 한 뒤 가드 검사를 수행한다.

    PRD §3.5.1 (B-2) — 자연어 분기 응답이 GitHub PR/이슈 URL 을 인용해도
    `find_forbidden_keywords` 가 URL 안의 저장소 slug 토큰에 매치되지 않도록
    URL 을 일시 치환한다. 검사는 escape 된 본문에 대해 돌리며, 통과 시 원복한
    텍스트(=원본 URL 포함) 를 반환한다.

    - URL 이 없으면 `guard_text` 와 동일하게 동작.
    - 매치 발견 시 placeholder 가 발사되지 않도록 fallback 으로 치환.
    - 정상 통과 시 placeholder 가 본문에 남지 않도록 반드시 원복.
    """
    if not text:
        return text or ""
    escaped, urls = with_urls_escaped(text)
    if find_forbidden_keywords(escaped):
        return FALLBACK_RESPONSE
    return restore_urls(escaped, urls)


def guard_text_strict(text: str | None, *, context: str = "") -> None:
    """빌드 시점/테스트 시점 검사용 strict 가드. 매치 시 AssertionError.

    `slack_renderer` 모듈 안에서 정의된 모든 정적 템플릿이 정책을 위반하지 않는지
    테스트로 보증하기 위한 진입점.
    """
    assert_no_forbidden(text, context=context)


# ---------------------------------------------------------------------------
# Block Kit 빌더
# ---------------------------------------------------------------------------


def build_action_value(idempotency_key: str, job_id: int) -> str:
    """Block Kit `value` 에 묶을 식별자 (replay 방지) — legacy 포맷.

    포맷: `<idempotency_key>:<job_id>`. 호출 측에서 split 해 검증한다.
    PR 번호를 포함하는 신규 포맷은 `build_action_value_v2` 를 사용한다.
    """
    if not idempotency_key:
        raise ValueError("idempotency_key 가 비어 있습니다.")
    return f"{idempotency_key}:{int(job_id)}"


def parse_action_value(value: str | None) -> tuple[str, int] | None:
    """`build_action_value` 의 역. 형식이 다르면 None."""
    if not value or ":" not in value:
        return None
    key, _, raw_id = value.rpartition(":")
    try:
        return key, int(raw_id)
    except ValueError:
        return None


def build_action_value_v2(
    *,
    pr_number: int,
    idempotency_key: str,
    job_id: int,
) -> str:
    """Block Kit `value` 신규 포맷 (PRD `dev-relay-agent-integration.md` §3.2).

    포맷: `pr=<N>;key=<idempotency_key>;job=<job_id>`.
    `[머지 검토]` / `[승인]` / `[상세 보기]` 모든 신규 버튼이 본 포맷을 사용한다.

    Slack `value` 필드 한도(2000자) 안에서 동작 — `idempotency_key` 가 Slack
    `client_msg_id`(UUID 36자) 라 안전하다.
    """
    if not idempotency_key:
        raise ValueError("idempotency_key 가 비어 있습니다.")
    if ";" in idempotency_key or "=" in idempotency_key:
        raise ValueError("idempotency_key 에 구분자가 포함되어 있습니다.")
    return f"pr={int(pr_number)};key={idempotency_key};job={int(job_id)}"


@dataclass(frozen=True, slots=True)
class ActionPayloadV2:
    """`build_action_value_v2` 의 파싱 결과."""

    pr_number: int
    idempotency_key: str
    job_id: int


def parse_action_value_v2(value: str | None) -> ActionPayloadV2 | None:
    """`build_action_value_v2` 의 역. 형식이 다르면 None.

    파싱 실패 사유는 호출 측에서 audit 에 기록하지 않는다 (단순 형식 검증 실패).
    """
    if not value:
        return None
    parts = value.split(";")
    fields: dict[str, str] = {}
    for part in parts:
        if "=" not in part:
            return None
        key, _, val = part.partition("=")
        fields[key] = val
    if {"pr", "key", "job"} - set(fields):
        return None
    try:
        pr_number = int(fields["pr"])
        job_id = int(fields["job"])
    except ValueError:
        return None
    if not fields["key"]:
        return None
    return ActionPayloadV2(
        pr_number=pr_number,
        idempotency_key=fields["key"],
        job_id=job_id,
    )


def build_review_result_blocks(
    *,
    pr_number: int,
    summary: str,
    findings: list[str] | None,
    idempotency_key: str,
    job_id: int,
) -> list[dict[str, Any]]:
    """`review pr <N>` 결과 메시지 (Block Kit 버튼 포함, AC-4).

    - summary, findings 는 외부 노출 텍스트이므로 `guard_text` 통과.
    - 버튼 라벨은 정적 상수 — 모듈 import 시점에 strict 검증한다 (테스트로 보강).
    """
    safe_summary = guard_text(summary)
    safe_findings = [guard_text(f) for f in (findings or [])][:3]

    blocks: list[dict[str, Any]] = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*PR #{pr_number} 리뷰 결과*\n{safe_summary}",
            },
        }
    ]
    if safe_findings:
        bullet = "\n".join(f"- {item}" for item in safe_findings)
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*발견 사항*\n{bullet}"},
            }
        )
    else:
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "특이사항 없음"},
            }
        )

    action_value = build_action_value_v2(
        pr_number=pr_number,
        idempotency_key=idempotency_key,
        job_id=job_id,
    )
    blocks.append(
        {
            "type": "actions",
            "block_id": f"review_actions_{job_id}",
            "elements": [
                {
                    "type": "button",
                    "action_id": "merge_review",
                    "text": {"type": "plain_text", "text": "머지 검토"},
                    "value": action_value,
                    "style": "primary",
                },
                {
                    "type": "button",
                    "action_id": "view_details",
                    "text": {"type": "plain_text", "text": "상세 보기"},
                    "value": action_value,
                },
            ],
        }
    )
    return blocks


def build_merge_confirm_blocks(
    *,
    pr_number: int,
    idempotency_key: str,
    job_id: int,
) -> list[dict[str, Any]]:
    """머지 confirm 다이얼로그 (AC-5 1단계).

    PRD `dev-relay-agent-integration.md` §3.2 / §3.3 — `[승인]` 핸들러가 PR
    번호를 페이로드에서 직접 복원할 수 있도록 v2 포맷을 사용한다.
    """
    action_value = build_action_value_v2(
        pr_number=pr_number,
        idempotency_key=idempotency_key,
        job_id=job_id,
    )
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"PR #{pr_number} 머지를 진행할까요?",
            },
        },
        {
            "type": "actions",
            "block_id": f"merge_confirm_{job_id}",
            "elements": [
                {
                    "type": "button",
                    "action_id": "approve_merge",
                    "text": {"type": "plain_text", "text": "승인"},
                    "value": action_value,
                    "style": "primary",
                },
                {
                    "type": "button",
                    "action_id": "cancel_merge",
                    "text": {"type": "plain_text", "text": "취소"},
                    "value": action_value,
                    "style": "danger",
                },
            ],
        },
    ]


def build_status_text(
    *,
    running: int,
    pending: int,
    last_pr_number: int | None,
) -> str:
    """`status` 응답 본문 (AC-2)."""
    if last_pr_number is None:
        last_line = "- 최근 처리 이력 없음"
    else:
        last_line = f"- 최근 완료 PR: #{last_pr_number}"
    body = (
        "현재 큐 현황\n"
        f"- 처리 중: {int(running)}건\n"
        f"- 대기: {int(pending)}건\n"
        f"{last_line}"
    )
    return guard_text(body)


def build_merge_result_text(
    *,
    pr_number: int,
    success: bool,
    detail: str | None = None,
) -> str:
    """머지 결과 보고 (AC-5)."""
    if success:
        body = f"PR #{pr_number} 머지 완료"
        if detail:
            body += f" ({detail})"
    else:
        body = f"PR #{pr_number} 머지 실패"
        if detail:
            body += f" — {detail}"
    return guard_text(body)


# ---------------------------------------------------------------------------
# 모듈 자체 정적 가드 — import 시점에 정적 템플릿이 정책을 위반하지 않는지 검증.
# ---------------------------------------------------------------------------


_STATIC_TEMPLATES: tuple[str, ...] = (
    FALLBACK_RESPONSE,
    TEMPLATE_QUEUE_ACCEPTED_REVIEW,
    TEMPLATE_QUEUE_ACCEPTED_MERGE,
    TEMPLATE_QUEUE_BUSY,
    TEMPLATE_RECOVERY_NOTICE,
    TEMPLATE_CANCEL_NOTICE,
    TEMPLATE_RATE_LIMIT,
    TEMPLATE_UNKNOWN_COMMAND,
    TEMPLATE_DESTRUCTIVE_BLOCKED,
    TEMPLATE_MERGE_CARVE_OUT_NOTICE,
    TEMPLATE_REVIEW_DETAIL_LOOKUP_FAILED,
    TEMPLATE_FAIL_DESTRUCTIVE_BLOCKED,
    TEMPLATE_FAIL_SDK_TIMEOUT,
    TEMPLATE_FAIL_GITHUB_UNAUTHORIZED,
    TEMPLATE_FAIL_GITHUB_UNPROCESSABLE,
    TEMPLATE_FAIL_COMPLIANCE_BLOCKED,
    TEMPLATE_FAIL_UNKNOWN,
)

for _template in _STATIC_TEMPLATES:
    # placeholder 토큰(`{pr_number}`, `{pending}`)은 단어 경계 안에 있어 정책 검사에
    # 영향 없음. 매치 시 import 가 실패하므로 회귀를 즉시 잡는다.
    guard_text_strict(_template, context="dev_relay.slack_renderer.template")
