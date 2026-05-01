"""코디네이터 발신자 화이트리스트·자기 메시지 판정 테스트 (AC-5, AC-9)."""

from __future__ import annotations

from ai.coordinator.auth import (
    is_allowed_sender,
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
