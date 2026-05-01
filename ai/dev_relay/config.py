"""
환경변수 로딩·검증 (Dev Manager).

PRD AC-9 / §3.7: 토큰 누락 또는 prefix 오류 시 한 줄 에러 메시지를 출력하고
exit code != 0 으로 종료. 토큰 값은 절대 출력·로깅하지 않는다.

코디네이터 `ai/coordinator/config.py` 와 동일한 패턴이지만, 환경변수 prefix·
기본 화이트리스트가 별도이므로 본 모듈로 분리 유지한다 (정책이 봇별로 갈릴 수 있음).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# 기본 화이트리스트 — PRD §3.8 / §6.2 (PM 지정 user id).
DEFAULT_ALLOWED_USER_IDS: tuple[str, ...] = ("U0AE7A54NHL",)

# 토큰 prefix 규약 — Slack / Anthropic 공식 문서 기반.
_BOT_TOKEN_PREFIX = "xoxb-"
_APP_TOKEN_PREFIX = "xapp-"
_ANTHROPIC_KEY_PREFIX = "sk-ant-"

# `.env.example` 의 placeholder 가 그대로 흘러들어와 prefix 검사를 통과해버려
# fail-fast 가 무력화되는 것을 방지. SSoT 는 본 frozenset 한 곳.
_PLACEHOLDER_TOKENS: frozenset[str] = frozenset(
    {
        "xoxb-여기에붙여넣기",
        "xapp-여기에붙여넣기",
        "sk-ant-여기에붙여넣기",
    }
)


class ConfigError(ValueError):
    """환경변수 누락·형식 오류. 메시지에 토큰 값을 포함하지 않는다."""


@dataclass(frozen=True, slots=True)
class DevRelayConfig:
    """런타임 설정 스냅샷. 토큰은 메모리에만 보관."""

    bot_token: str
    app_token: str
    anthropic_api_key: str
    allowed_user_ids: frozenset[str]
    log_level: str

    def with_masked_repr(self) -> str:
        """진단용 표현. 토큰은 prefix + 마스킹."""
        return (
            "DevRelayConfig("
            f"bot_token={mask_token(self.bot_token)}, "
            f"app_token={mask_token(self.app_token)}, "
            f"anthropic_api_key={mask_token(self.anthropic_api_key)}, "
            f"allowed_user_ids={sorted(self.allowed_user_ids)}, "
            f"log_level={self.log_level})"
        )


def mask_token(token: str | None) -> str:
    """토큰 마스킹 — prefix + `***` 만 남긴다.

    로그·진단 출력 어디에서도 평문 토큰이 새어 나가지 않도록 본 헬퍼를 거친다.
    """
    if not token:
        return "<empty>"
    for prefix in (_BOT_TOKEN_PREFIX, _APP_TOKEN_PREFIX, _ANTHROPIC_KEY_PREFIX):
        if token.startswith(prefix):
            return f"{prefix}***"
    return "***"


def _parse_allowed_ids(raw: str | None) -> frozenset[str]:
    """콤마 구분 user id 파싱. 빈 문자열·None 이면 기본값 사용."""
    if raw is None or not raw.strip():
        return frozenset(DEFAULT_ALLOWED_USER_IDS)
    ids = [piece.strip() for piece in raw.split(",")]
    cleaned = [piece for piece in ids if piece]
    if not cleaned:
        return frozenset(DEFAULT_ALLOWED_USER_IDS)
    return frozenset(cleaned)


def _require_token(
    source: dict[str, str], key: str, prefix: str
) -> str:
    """토큰 한 종류를 검증해 반환. 누락·prefix·placeholder 모두 차단."""
    raw = (source.get(key) or "").strip()
    if not raw:
        raise ConfigError(f"환경변수 {key} 가 설정되지 않았습니다.")
    if not raw.startswith(prefix):
        raise ConfigError(
            f"환경변수 {key} 의 prefix 가 올바르지 않습니다 (기대: '{prefix}')."
        )
    if raw in _PLACEHOLDER_TOKENS:
        raise ConfigError(
            f"환경변수 {key} 가 placeholder 값입니다. .env 를 실제 값으로 채우세요."
        )
    return raw


def load_config(env: dict[str, str] | None = None) -> DevRelayConfig:
    """
    환경변수에서 설정을 읽고 검증한다.

    누락·형식 오류는 `ConfigError` 로 raise. 호출자(`main`)가 잡아 한 줄 메시지로
    출력하고 비정상 exit 한다.
    """
    source = env if env is not None else os.environ

    bot_token = _require_token(source, "SLACK_DEV_RELAY_BOT_TOKEN", _BOT_TOKEN_PREFIX)
    app_token = _require_token(source, "SLACK_DEV_RELAY_APP_TOKEN", _APP_TOKEN_PREFIX)
    anthropic_key = _require_token(source, "ANTHROPIC_API_KEY", _ANTHROPIC_KEY_PREFIX)

    allowed_raw = source.get("DEV_RELAY_ALLOWED_USER_IDS")
    log_level = (source.get("LOG_LEVEL") or "INFO").strip().upper()

    return DevRelayConfig(
        bot_token=bot_token,
        app_token=app_token,
        anthropic_api_key=anthropic_key,
        allowed_user_ids=_parse_allowed_ids(allowed_raw),
        log_level=log_level,
    )
