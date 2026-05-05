"""auth 화이트리스트 / 마스킹 단위 테스트 (PRD §3.8 / AC-7)."""

from __future__ import annotations

import pytest

from ai.dev_relay.auth import (
    extract_action_user_id,
    extract_sender,
    is_allowed_sender,
    is_handleable_message_subtype,
    is_self_message,
    mask_user_id,
)


ALLOWED = frozenset({"U0AE7A54NHL"})


class TestIsAllowedSender:
    def test_allowed_user(self):
        assert is_allowed_sender("U0AE7A54NHL", ALLOWED) is True

    def test_disallowed_user(self):
        assert is_allowed_sender("UOTHER0001", ALLOWED) is False

    def test_empty_user(self):
        assert is_allowed_sender("", ALLOWED) is False
        assert is_allowed_sender(None, ALLOWED) is False

    def test_empty_allowlist(self):
        assert is_allowed_sender("U0AE7A54NHL", frozenset()) is False


class TestIsSelfMessage:
    def test_bot_id_present(self):
        event = {"bot_id": "B12345", "user": "UOTHER", "channel_type": "im"}
        assert is_self_message(event, "UBOT001") is True

    def test_user_matches_self(self):
        event = {"user": "UBOT001", "channel_type": "im"}
        assert is_self_message(event, "UBOT001") is True

    def test_subtype_bot_message(self):
        event = {"subtype": "bot_message", "channel_type": "im"}
        assert is_self_message(event, "UBOT001") is True

    def test_clean_message(self):
        event = {"user": "U0AE7A54NHL", "channel_type": "im"}
        assert is_self_message(event, "UBOT001") is False


class TestExtractSender:
    def test_top_level(self):
        assert extract_sender({"user": "U0AE7A54NHL"}) == "U0AE7A54NHL"

    def test_nested_message_changed(self):
        event = {"subtype": "message_changed", "message": {"user": "U0AE7A54NHL"}}
        assert extract_sender(event) == "U0AE7A54NHL"

    def test_previous_message_for_deletion(self):
        event = {
            "subtype": "message_deleted",
            "previous_message": {"user": "U0AE7A54NHL"},
        }
        assert extract_sender(event) == "U0AE7A54NHL"

    def test_returns_none_when_missing(self):
        assert extract_sender({}) is None


class TestIsHandleableMessageSubtype:
    @pytest.mark.parametrize(
        "event",
        [
            {},
            {"subtype": None},
            {"subtype": ""},
        ],
    )
    def test_handleable(self, event: dict):
        assert is_handleable_message_subtype(event) is True

    @pytest.mark.parametrize(
        "event",
        [
            {"subtype": "message_changed"},
            {"subtype": "message_deleted"},
            {"subtype": "bot_message"},
            {"subtype": "channel_join"},
            {"subtype": "thread_broadcast"},
        ],
    )
    def test_not_handleable(self, event: dict):
        assert is_handleable_message_subtype(event) is False


class TestMaskUserId:
    def test_long_id_masks_after_six(self):
        # PRD §3.6 — 앞 6자만 보존.
        assert mask_user_id("U0AE7A54NHL") == "U0AE7A***"

    def test_short_id(self):
        assert mask_user_id("U123") == "***"

    def test_exactly_six_chars(self):
        # 6자 이하는 모두 마스킹.
        assert mask_user_id("U12345") == "***"

    def test_seven_chars(self):
        assert mask_user_id("U123456") == "U12345***"

    def test_empty(self):
        assert mask_user_id("") == "<unknown>"
        assert mask_user_id(None) == "<unknown>"


class TestExtractActionUserId:
    def test_extracts_id(self):
        payload = {"user": {"id": "U0AE7A54NHL", "name": "hayoung"}}
        assert extract_action_user_id(payload) == "U0AE7A54NHL"

    def test_missing_user(self):
        assert extract_action_user_id({}) is None

    def test_missing_id_field(self):
        assert extract_action_user_id({"user": {}}) is None

    def test_none_payload(self):
        # 타입 가드.
        assert extract_action_user_id(None) is None  # type: ignore[arg-type]
