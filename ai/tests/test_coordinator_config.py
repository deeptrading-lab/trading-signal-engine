"""코디네이터 환경변수 로딩·검증 테스트 (AC-7)."""

from __future__ import annotations

import pytest

from ai.coordinator.config import (
    DEFAULT_ALLOWED_USER_IDS,
    ConfigError,
    CoordinatorConfig,
    load_config,
)


VALID_BOT = "xoxb-fake-bot-token-123"
VALID_APP = "xapp-fake-app-token-456"


class TestLoadConfig:
    """`load_config` — fail-fast 검증."""

    def test_load_with_valid_env(self):
        env = {
            "SLACK_BOT_TOKEN": VALID_BOT,
            "SLACK_APP_TOKEN": VALID_APP,
        }
        cfg = load_config(env)
        assert isinstance(cfg, CoordinatorConfig)
        assert cfg.bot_token == VALID_BOT
        assert cfg.app_token == VALID_APP
        assert cfg.allowed_user_ids == frozenset(DEFAULT_ALLOWED_USER_IDS)
        assert cfg.log_level == "INFO"

    def test_missing_bot_token_raises(self):
        with pytest.raises(ConfigError) as exc_info:
            load_config({"SLACK_APP_TOKEN": VALID_APP})
        assert "SLACK_BOT_TOKEN" in str(exc_info.value)

    def test_missing_app_token_raises(self):
        with pytest.raises(ConfigError) as exc_info:
            load_config({"SLACK_BOT_TOKEN": VALID_BOT})
        assert "SLACK_APP_TOKEN" in str(exc_info.value)

    def test_empty_bot_token_raises(self):
        with pytest.raises(ConfigError):
            load_config({"SLACK_BOT_TOKEN": "   ", "SLACK_APP_TOKEN": VALID_APP})

    def test_wrong_bot_token_prefix_raises(self):
        with pytest.raises(ConfigError) as exc_info:
            load_config(
                {
                    "SLACK_BOT_TOKEN": "xapp-wrong-prefix",
                    "SLACK_APP_TOKEN": VALID_APP,
                }
            )
        assert "SLACK_BOT_TOKEN" in str(exc_info.value)
        assert "xoxb-" in str(exc_info.value)

    def test_wrong_app_token_prefix_raises(self):
        with pytest.raises(ConfigError) as exc_info:
            load_config(
                {
                    "SLACK_BOT_TOKEN": VALID_BOT,
                    "SLACK_APP_TOKEN": "xoxb-wrong-prefix",
                }
            )
        assert "SLACK_APP_TOKEN" in str(exc_info.value)
        assert "xapp-" in str(exc_info.value)

    def test_error_message_does_not_contain_token_value(self):
        """AC-7: 토큰 값은 마스킹되거나 출력되지 않는다."""
        secret_value = "xoxb-super-secret-token-DO-NOT-LEAK"
        with pytest.raises(ConfigError) as exc_info:
            load_config({"SLACK_BOT_TOKEN": secret_value})
        # SLACK_APP_TOKEN 누락이 먼저 잡혀도 OK. 어떤 메시지든 토큰 값은 없어야.
        assert secret_value not in str(exc_info.value)

    def test_custom_allowed_user_ids(self):
        env = {
            "SLACK_BOT_TOKEN": VALID_BOT,
            "SLACK_APP_TOKEN": VALID_APP,
            "SLACK_ALLOWED_USER_IDS": "U111, U222 ,U333",
        }
        cfg = load_config(env)
        assert cfg.allowed_user_ids == frozenset({"U111", "U222", "U333"})

    def test_blank_allowed_user_ids_falls_back_to_default(self):
        env = {
            "SLACK_BOT_TOKEN": VALID_BOT,
            "SLACK_APP_TOKEN": VALID_APP,
            "SLACK_ALLOWED_USER_IDS": "   ",
        }
        cfg = load_config(env)
        assert cfg.allowed_user_ids == frozenset(DEFAULT_ALLOWED_USER_IDS)

    def test_custom_log_level(self):
        env = {
            "SLACK_BOT_TOKEN": VALID_BOT,
            "SLACK_APP_TOKEN": VALID_APP,
            "LOG_LEVEL": "debug",
        }
        cfg = load_config(env)
        assert cfg.log_level == "DEBUG"

    def test_masked_repr_does_not_leak_token(self):
        cfg = load_config(
            {
                "SLACK_BOT_TOKEN": "xoxb-very-secret-bot",
                "SLACK_APP_TOKEN": "xapp-very-secret-app",
            }
        )
        repr_str = cfg.with_masked_repr()
        assert "very-secret-bot" not in repr_str
        assert "very-secret-app" not in repr_str
        assert "xoxb-***" in repr_str
        assert "xapp-***" in repr_str

    def test_default_user_id_includes_pm(self):
        """PRD §3.1: 기본 화이트리스트는 PM user id 포함."""
        assert "U0AE7A54NHL" in DEFAULT_ALLOWED_USER_IDS
