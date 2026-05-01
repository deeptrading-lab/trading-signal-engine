"""
발신자 / 버튼 액션 화이트리스트 판정 (Dev Relay).

PRD AC-7 / §3.8: 화이트리스트 외 user_id 에서 오는 메시지·Block Kit 액션은
모두 무시. 봇 자기 메시지(infinite loop 방지)도 본 모듈에서 차단한다 (AC-17).

코디네이터 `ai/coordinator/auth.py` 의 함수들을 그대로 재사용해도 충분하지만,
PRD §3.2 가 "정책이 봇별로 갈릴 수 있음" 을 이유로 별도 모듈로 두기를 명시했으므로
얇은 위임 wrapper 만 유지한다 — 정책 단일화는 import 로 보장.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from ai.coordinator.auth import (
    extract_sender as _coordinator_extract_sender,
    is_allowed_sender as _coordinator_is_allowed_sender,
    is_handleable_message_subtype as _coordinator_is_handleable_message_subtype,
    is_self_message as _coordinator_is_self_message,
)


def is_self_message(event: Mapping[str, Any], self_bot_user_id: str | None) -> bool:
    """봇 자기 메시지 판정 (AC-17)."""
    return _coordinator_is_self_message(event, self_bot_user_id)


def extract_sender(event: Mapping[str, Any]) -> str | None:
    """이벤트 페이로드에서 발신자 user id 추출."""
    return _coordinator_extract_sender(event)


def is_handleable_message_subtype(event: Mapping[str, Any]) -> bool:
    """명령 라우팅 대상 이벤트인지 판정 (편집·삭제·시스템 메시지 등 무시)."""
    return _coordinator_is_handleable_message_subtype(event)


def is_allowed_sender(
    user_id: str | None,
    allowed_user_ids: Iterable[str],
) -> bool:
    """화이트리스트 판정 (AC-7). 빈 입력은 거부."""
    return _coordinator_is_allowed_sender(user_id, allowed_user_ids)


def mask_user_id(user_id: str | None) -> str:
    """audit log / 외부 노출 로그용 user_id 마스킹.

    PRD §3.6: 앞 6자만 보존하고 뒤는 `***` 로 마스킹.
    코디네이터의 마스킹 헬퍼는 앞 4자 정책이라 본 봇 PRD 와 다르다 — 별도 정의.
    """
    if not user_id:
        return "<unknown>"
    if len(user_id) <= 6:
        return "***"
    return f"{user_id[:6]}***"


def extract_action_user_id(payload: Mapping[str, Any]) -> str | None:
    """Block Kit `block_actions` payload 에서 클릭한 user_id 추출 (AC-7).

    Slack Bolt 페이로드는 `payload["user"]["id"]` 형태로 user 를 담는다.
    """
    if not isinstance(payload, Mapping):
        return None
    user = payload.get("user")
    if isinstance(user, Mapping):
        uid = user.get("id")
        if uid:
            return uid
    return None
