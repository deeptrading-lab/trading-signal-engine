"""환경변수 로딩·검증 단위 테스트 (PRD AC-9 / §3.7)."""

from __future__ import annotations

import pytest

from ai.dev_relay.config import (
    AuthMode,
    ConfigError,
    DevRelayConfig,
    load_config,
    mask_token,
)


_VALID_BOT = "xoxb-1234567890-abcdef"
_VALID_APP = "xapp-1-AAA-BBB-CCC"
_VALID_KEY = "sk-ant-api03-zzzz"


def _base_env(**overrides: str) -> dict[str, str]:
    env = {
        "SLACK_DEV_RELAY_BOT_TOKEN": _VALID_BOT,
        "SLACK_DEV_RELAY_APP_TOKEN": _VALID_APP,
    }
    env.update(overrides)
    return env


class TestRequiredTokens:
    def test_loads_with_minimum_env(self):
        cfg = load_config(_base_env())
        assert cfg.bot_token == _VALID_BOT
        assert cfg.app_token == _VALID_APP
        assert cfg.anthropic_api_key is None

    def test_missing_bot_token_raises(self):
        env = _base_env()
        env.pop("SLACK_DEV_RELAY_BOT_TOKEN")
        with pytest.raises(ConfigError):
            load_config(env)

    def test_missing_app_token_raises(self):
        env = _base_env()
        env.pop("SLACK_DEV_RELAY_APP_TOKEN")
        with pytest.raises(ConfigError):
            load_config(env)

    @pytest.mark.parametrize(
        "key,bad_value",
        [
            ("SLACK_DEV_RELAY_BOT_TOKEN", "wrong-prefix-xyz"),
            ("SLACK_DEV_RELAY_APP_TOKEN", "xoxb-wrong-prefix"),
        ],
    )
    def test_bad_prefix_raises(self, key: str, bad_value: str):
        env = _base_env(**{key: bad_value})
        with pytest.raises(ConfigError):
            load_config(env)

    @pytest.mark.parametrize(
        "key,placeholder",
        [
            ("SLACK_DEV_RELAY_BOT_TOKEN", "xoxb-여기에붙여넣기"),
            ("SLACK_DEV_RELAY_APP_TOKEN", "xapp-여기에붙여넣기"),
        ],
    )
    def test_placeholder_raises(self, key: str, placeholder: str):
        env = _base_env(**{key: placeholder})
        with pytest.raises(ConfigError):
            load_config(env)


class TestOptionalAnthropicKey:
    """AC-9 (b/c): API 키는 선택, 잘못된 형식은 silent 무시 X."""

    def test_missing_yields_subscription_mode(self):
        cfg = load_config(_base_env())
        assert cfg.anthropic_api_key is None
        assert cfg.auth_mode is AuthMode.SUBSCRIPTION

    def test_empty_string_yields_subscription_mode(self):
        cfg = load_config(_base_env(ANTHROPIC_API_KEY=""))
        assert cfg.anthropic_api_key is None
        assert cfg.auth_mode is AuthMode.SUBSCRIPTION

    def test_whitespace_only_yields_subscription_mode(self):
        cfg = load_config(_base_env(ANTHROPIC_API_KEY="   "))
        assert cfg.anthropic_api_key is None
        assert cfg.auth_mode is AuthMode.SUBSCRIPTION

    def test_valid_key_yields_api_key_mode(self):
        cfg = load_config(_base_env(ANTHROPIC_API_KEY=_VALID_KEY))
        assert cfg.anthropic_api_key == _VALID_KEY
        assert cfg.auth_mode is AuthMode.API_KEY

    def test_bad_prefix_raises(self):
        with pytest.raises(ConfigError):
            load_config(_base_env(ANTHROPIC_API_KEY="not-a-valid-key"))

    def test_placeholder_raises(self):
        with pytest.raises(ConfigError):
            load_config(_base_env(ANTHROPIC_API_KEY="sk-ant-여기에붙여넣기"))


class TestAllowedUserIds:
    def test_default_when_missing(self):
        cfg = load_config(_base_env())
        assert "U0AE7A54NHL" in cfg.allowed_user_ids

    def test_explicit_overrides_default(self):
        cfg = load_config(_base_env(DEV_RELAY_ALLOWED_USER_IDS="UAAA,UBBB"))
        assert cfg.allowed_user_ids == frozenset({"UAAA", "UBBB"})

    def test_blank_falls_back_to_default(self):
        cfg = load_config(_base_env(DEV_RELAY_ALLOWED_USER_IDS="   "))
        assert "U0AE7A54NHL" in cfg.allowed_user_ids


class TestMaskTokenAndRepr:
    def test_mask_preserves_prefix(self):
        assert mask_token(_VALID_BOT) == "xoxb-***"
        assert mask_token(_VALID_APP) == "xapp-***"
        assert mask_token(_VALID_KEY) == "sk-ant-***"

    def test_mask_handles_none_and_empty(self):
        assert mask_token(None) == "<empty>"
        assert mask_token("") == "<empty>"

    def test_repr_does_not_leak_tokens(self):
        cfg = load_config(_base_env(ANTHROPIC_API_KEY=_VALID_KEY))
        rendered = cfg.with_masked_repr()
        assert _VALID_BOT not in rendered
        assert _VALID_APP not in rendered
        assert _VALID_KEY not in rendered
        assert "auth_mode=api_key" in rendered

    def test_repr_subscription_mode(self):
        cfg = load_config(_base_env())
        rendered = cfg.with_masked_repr()
        assert "auth_mode=subscription" in rendered


class TestDataclass:
    def test_is_frozen(self):
        cfg = load_config(_base_env())
        with pytest.raises(Exception):
            cfg.bot_token = "mutated"  # type: ignore[misc]

    def test_auth_mode_is_property(self):
        cfg = DevRelayConfig(
            bot_token=_VALID_BOT,
            app_token=_VALID_APP,
            anthropic_api_key=None,
            allowed_user_ids=frozenset({"U0AE7A54NHL"}),
            log_level="INFO",
        )
        assert cfg.auth_mode is AuthMode.SUBSCRIPTION
