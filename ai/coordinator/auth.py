"""
발신자 화이트리스트 판정.

PRD AC-5 / AC-9: 화이트리스트 외 사용자, 또는 봇 자기 자신의 메시지는 무시.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


def is_self_message(event: Mapping[str, Any], self_bot_user_id: str | None) -> bool:
    """
    이벤트가 봇 자신이 보낸 메시지인지 판정 (AC-9).

    판정 기준:
    - `bot_id` 필드가 채워져 있다 → 어떤 봇이 보낸 메시지 (자기 포함).
    - `user` 필드가 봇 자신의 user id 와 같다.
    - `subtype == "bot_message"` 인 경우.

    어느 하나라도 만족하면 True.
    """
    if not isinstance(event, Mapping):
        return False

    if event.get("bot_id"):
        return True

    if event.get("subtype") == "bot_message":
        return True

    if self_bot_user_id and event.get("user") == self_bot_user_id:
        return True

    return False


def is_handleable_message_subtype(event: Mapping[str, Any]) -> bool:
    """
    명령 라우팅 대상 이벤트인지 판정 (PRD: slack-message-subtype-guard §3.1).

    whitelist 정책 — 일반 사용자 텍스트 메시지만 True 로 판정한다:
    - `subtype` 키가 이벤트에 없는 경우
    - `subtype` 값이 None 인 경우
    - `subtype` 값이 빈 문자열인 경우

    그 외 모든 subtype(`message_changed`, `message_deleted`, `thread_broadcast`,
    `file_share`, `bot_message`, `channel_join`, `channel_leave`, 그리고 알려지지
    않은 신규 subtype 등)은 False 를 반환해 보수적으로 무시한다.

    부수효과 없음 (로깅은 호출부에서 수행).
    """
    if not isinstance(event, Mapping):
        return False
    subtype = event.get("subtype")
    if subtype is None or subtype == "":
        return True
    return False


def is_allowed_sender(
    user_id: str | None,
    allowed_user_ids: Iterable[str],
) -> bool:
    """
    발신자가 화이트리스트에 포함되는지 판정 (AC-5).

    `user_id` 가 비어 있거나 None 이면 거부.
    `allowed_user_ids` 가 비어 있으면 거부 (기본값은 config 단계에서 채운다).
    """
    if not user_id:
        return False
    allowed_set = set(allowed_user_ids)
    if not allowed_set:
        return False
    return user_id in allowed_set


def mask_user_id(user_id: str | None) -> str:
    """로그용 user id 부분 마스킹. 외부 노출 시 식별자 일부만 노출."""
    if not user_id:
        return "<unknown>"
    if len(user_id) <= 4:
        return "***"
    return f"{user_id[:4]}***"
