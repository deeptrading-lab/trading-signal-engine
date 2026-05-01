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
