from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class LLMSettings:
    openai_api_key_configured: bool
    anthropic_api_key_configured: bool
    news_model: str
    brief_model: str
    anthropic_brief_model: str
    monthly_billing_limit_usd: float
    daily_cost_limit_usd: float
    news_refresh_max_articles: int
    news_refresh_max_input_tokens: int
    morning_brief_max_output_tokens: int
    manual_brief_max_output_tokens: int
    timezone: str


def load_openai_settings() -> LLMSettings:
    return load_llm_settings()


def load_llm_settings() -> LLMSettings:
    return LLMSettings(
        openai_api_key_configured=bool(os.getenv("OPENAI_API_KEY")),
        anthropic_api_key_configured=bool(os.getenv("ANTHROPIC_API_KEY")),
        news_model=os.getenv("OPENAI_NEWS_MODEL", "gpt-5.4-nano"),
        brief_model=os.getenv("OPENAI_BRIEF_MODEL", "gpt-5.4-mini"),
        anthropic_brief_model=os.getenv("ANTHROPIC_BRIEF_MODEL", "claude-3-5-haiku-20241022"),
        monthly_billing_limit_usd=_float_env("OPENAI_MONTHLY_BILLING_LIMIT_USD", 20.0),
        daily_cost_limit_usd=_float_env("OPENAI_DAILY_COST_LIMIT_USD", 0.50),
        news_refresh_max_articles=_int_env("NEWS_REFRESH_MAX_ARTICLES", 8),
        news_refresh_max_input_tokens=_int_env("NEWS_REFRESH_MAX_INPUT_TOKENS", 6000),
        morning_brief_max_output_tokens=_int_env("MORNING_BRIEF_MAX_OUTPUT_TOKENS", 900),
        manual_brief_max_output_tokens=_int_env("MANUAL_BRIEF_MAX_OUTPUT_TOKENS", 1200),
        timezone=os.getenv("BITCOIN_SIGNAL_TIMEZONE", "Asia/Tokyo"),
    )


def _float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    if value in (None, ""):
        return default
    parsed = float(value)
    if parsed < 0:
        raise ValueError(f"{name} must be non-negative")
    return parsed


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value in (None, ""):
        return default
    parsed = int(value)
    if parsed < 0:
        raise ValueError(f"{name} must be non-negative")
    return parsed
