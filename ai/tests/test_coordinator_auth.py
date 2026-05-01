"""코디네이터 발신자 화이트리스트·자기 메시지 판정 테스트 (AC-5, AC-9)."""

from __future__ import annotations

from ai.coordinator.auth import (
    extract_sender,
    is_allowed_sender,
    is_handleable_message_subtype,
    is_self_message,
    mask_user_id,
)


class TestIsAllowedSender:
    """AC-5: 화이트리스트 판정."""

    def test_allowed_user_returns_true(self):
        assert is_allowed_sender("U0AE7A54NHL", {"U0AE7A54NHL"}) is True

    def test_disallowed_user_returns_false(self):
        assert is_allowed_sender("U_OTHER", {"U0AE7A54NHL"}) is False

    def test_none_user_returns_false(self):
        assert is_allowed_sender(None, {"U0AE7A54NHL"}) is False

    def test_empty_user_returns_false(self):
        assert is_allowed_sender("", {"U0AE7A54NHL"}) is False

    def test_empty_whitelist_returns_false(self):
        assert is_allowed_sender("U0AE7A54NHL", set()) is False

    def test_multiple_allowed_users(self):
        allowed = {"U_AAA", "U_BBB", "U_CCC"}
        assert is_allowed_sender("U_BBB", allowed) is True
        assert is_allowed_sender("U_DDD", allowed) is False

    def test_accepts_frozenset(self):
        assert is_allowed_sender("U_X", frozenset({"U_X"})) is True

    def test_accepts_list(self):
        assert is_allowed_sender("U_X", ["U_X", "U_Y"]) is True


class TestIsSelfMessage:
    """AC-9: 봇 자기 메시지 판정."""

    def test_event_with_bot_id_is_self(self):
        event = {"bot_id": "B12345", "user": "U_X"}
        assert is_self_message(event, self_bot_user_id="U_BOT") is True

    def test_event_with_bot_message_subtype_is_self(self):
        event = {"subtype": "bot_message", "user": "U_X"}
        assert is_self_message(event, self_bot_user_id=None) is True

    def test_event_user_matches_self_bot_user_id(self):
        event = {"user": "U_BOT"}
        assert is_self_message(event, self_bot_user_id="U_BOT") is True

    def test_normal_user_event_is_not_self(self):
        event = {"user": "U0AE7A54NHL", "text": "ping"}
        assert is_self_message(event, self_bot_user_id="U_BOT") is False

    def test_no_self_id_and_no_bot_id_is_not_self(self):
        event = {"user": "U0AE7A54NHL", "text": "ping"}
        assert is_self_message(event, self_bot_user_id=None) is False

    def test_non_mapping_input_is_not_self(self):
        assert is_self_message(None, "U_BOT") is False  # type: ignore[arg-type]
        assert is_self_message("not a dict", "U_BOT") is False  # type: ignore[arg-type]


class TestIsHandleableMessageSubtype:
    """PRD slack-message-subtype-guard §3.1: subtype whitelist 가드."""

    def test_event_without_subtype_key_is_handleable(self):
        # T-1: subtype 키가 아예 없는 일반 메시지.
        event = {"type": "message", "text": "ping"}
        assert is_handleable_message_subtype(event) is True

    def test_event_with_subtype_none_is_handleable(self):
        # T-2: subtype 값이 None.
        event = {"type": "message", "subtype": None, "text": "ping"}
        assert is_handleable_message_subtype(event) is True

    def test_event_with_subtype_empty_string_is_handleable(self):
        # T-3: subtype 값이 빈 문자열.
        event = {"type": "message", "subtype": "", "text": "ping"}
        assert is_handleable_message_subtype(event) is True

    def test_message_changed_is_not_handleable(self):
        # T-4: 메시지 편집 이벤트는 무시.
        event = {
            "type": "message",
            "subtype": "message_changed",
            "message": {"text": "수정된 본문"},
        }
        assert is_handleable_message_subtype(event) is False

    def test_message_deleted_is_not_handleable(self):
        # T-5: 메시지 삭제 이벤트는 무시.
        event = {"type": "message", "subtype": "message_deleted"}
        assert is_handleable_message_subtype(event) is False

    def test_bot_message_is_not_handleable(self):
        # T-6: 다른 봇/외부 통합이 보낸 메시지.
        event = {
            "type": "message",
            "subtype": "bot_message",
            "user": "U_OTHER",
            "text": "외부 알림",
        }
        assert is_handleable_message_subtype(event) is False

    def test_unknown_future_subtype_is_not_handleable(self):
        # T-7: 알려지지 않은 신규 subtype 도 보수적(whitelist)으로 거부.
        event = {"type": "message", "subtype": "foo_unknown_future"}
        assert is_handleable_message_subtype(event) is False

    def test_non_mapping_input_is_not_handleable(self):
        # 방어적: dict 가 아닌 입력은 즉시 False.
        assert is_handleable_message_subtype(None) is False  # type: ignore[arg-type]
        assert is_handleable_message_subtype("not a dict") is False  # type: ignore[arg-type]


class TestMaskUserId:
    """로그용 user id 마스킹."""

    def test_masks_long_id(self):
        assert mask_user_id("U0AE7A54NHL") == "U0AE***"

    def test_short_id_fully_masked(self):
        assert mask_user_id("U12") == "***"

    def test_none_returns_unknown(self):
        assert mask_user_id(None) == "<unknown>"

    def test_empty_returns_unknown(self):
        assert mask_user_id("") == "<unknown>"


class TestExtractSender:
    """subtype 별 user 위치 차이 보정 — message_changed/message_deleted 등에서 실 발신자 추출."""

    def test_top_level_user_returned(self):
        assert extract_sender({"user": "U_AAA"}) == "U_AAA"

    def test_message_changed_uses_nested_message_user(self):
        event = {
            "type": "message",
            "subtype": "message_changed",
            "message": {"user": "U_BBB", "text": "edited"},
            "previous_message": {"user": "U_BBB", "text": "old"},
        }
        assert extract_sender(event) == "U_BBB"

    def test_message_deleted_uses_previous_message_user(self):
        event = {
            "type": "message",
            "subtype": "message_deleted",
            "previous_message": {"user": "U_CCC", "text": "deleted"},
        }
        assert extract_sender(event) == "U_CCC"

    def test_top_level_user_takes_precedence_over_nested(self):
        event = {
            "user": "U_TOP",
            "message": {"user": "U_NESTED"},
            "previous_message": {"user": "U_PREV"},
        }
        assert extract_sender(event) == "U_TOP"

    def test_no_user_anywhere_returns_none(self):
        assert extract_sender({"type": "message"}) is None

    def test_empty_user_falls_through_to_nested(self):
        event = {"user": "", "message": {"user": "U_FALLBACK"}}
        assert extract_sender(event) == "U_FALLBACK"

    def test_non_mapping_returns_none(self):
        assert extract_sender(None) is None  # type: ignore[arg-type]
        assert extract_sender("not a dict") is None  # type: ignore[arg-type]

    def test_non_mapping_nested_message_ignored(self):
        event = {"message": "broken", "previous_message": {"user": "U_PREV"}}
        assert extract_sender(event) == "U_PREV"
