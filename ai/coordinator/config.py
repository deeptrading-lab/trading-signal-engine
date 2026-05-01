"""
환경변수 로딩·검증.

PRD AC-7: 토큰 누락 또는 prefix 오류 시 한 줄 에러 메시지를 출력하고
exit code != 0 으로 종료. 토큰 값은 절대 출력·로깅하지 않는다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# 기본 화이트리스트 — PRD §3.1 / §6.2 (PM 지정 user id).
DEFAULT_ALLOWED_USER_IDS: tuple[str, ...] = ("U0AE7A54NHL",)

# 토큰 prefix 규약 — Slack 공식 문서 기반.
_BOT_TOKEN_PREFIX = "xoxb-"
_APP_TOKEN_PREFIX = "xapp-"

# `.env.example` 의 placeholder 표현이 그대로 흘러들어오면 prefix 검사를 통과해버려
# fail-fast 가 무력화된다. SSoT 는 본 frozenset 한 곳으로 두고, `.env.example` 표현이
# 바뀌더라도 코드 가드가 우선해 차단한다.
_PLACEHOLDER_TOKENS: frozenset[str] = frozenset(
    {
        "xoxb-여기에붙여넣기",
        "xapp-여기에붙여넣기",
    }
)


class ConfigError(ValueError):
    """환경변수 누락·형식 오류. 메시지에 토큰 값을 포함하지 않는다."""


@dataclass(frozen=True, slots=True)
class CoordinatorConfig:
    """런타임 설정 스냅샷. 토큰은 메모리에만 보관."""

    bot_token: str
    app_token: str
    allowed_user_ids: frozenset[str]
    log_level: str

    def with_masked_repr(self) -> str:
        """진단용 표현. 토큰은 prefix + 마스킹."""
        return (
            "CoordinatorConfig("
            f"bot_token={_mask(self.bot_token)}, "
            f"app_token={_mask(self.app_token)}, "
            f"allowed_user_ids={sorted(self.allowed_user_ids)}, "
            f"log_level={self.log_level})"
        )


def _mask(token: str) -> str:
    """토큰 마스킹 — prefix + `***` 만 남긴다."""
    if not token:
        return "<empty>"
    # prefix 끝까지만 노출하고 나머지는 마스킹.
    for prefix in (_BOT_TOKEN_PREFIX, _APP_TOKEN_PREFIX):
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


def load_config(env: dict[str, str] | None = None) -> CoordinatorConfig:
    """
    환경변수에서 설정을 읽고 검증한다.

    누락·형식 오류는 `ConfigError` 로 raise. 호출자(`main`)가 잡아 한 줄 메시지로
    출력하고 비정상 exit 한다.
    """
    source = env if env is not None else os.environ

    bot_token = (source.get("SLACK_BOT_TOKEN") or "").strip()
    app_token = (source.get("SLACK_APP_TOKEN") or "").strip()
    allowed_raw = source.get("SLACK_ALLOWED_USER_IDS")
    log_level = (source.get("LOG_LEVEL") or "INFO").strip().upper()

    if not bot_token:
        raise ConfigError(
            "환경변수 SLACK_BOT_TOKEN 이 설정되지 않았습니다."
        )
    if not bot_token.startswith(_BOT_TOKEN_PREFIX):
        raise ConfigError(
            "환경변수 SLACK_BOT_TOKEN 의 prefix 가 올바르지 않습니다 "
            f"(기대: '{_BOT_TOKEN_PREFIX}')."
        )
    if bot_token in _PLACEHOLDER_TOKENS:
        raise ConfigError(
            "환경변수 SLACK_BOT_TOKEN 가 placeholder 값입니다. "
            ".env 를 실제 토큰으로 채우세요."
        )

    if not app_token:
        raise ConfigError(
            "환경변수 SLACK_APP_TOKEN 이 설정되지 않았습니다."
        )
    if not app_token.startswith(_APP_TOKEN_PREFIX):
        raise ConfigError(
            "환경변수 SLACK_APP_TOKEN 의 prefix 가 올바르지 않습니다 "
            f"(기대: '{_APP_TOKEN_PREFIX}')."
        )
    if app_token in _PLACEHOLDER_TOKENS:
        raise ConfigError(
            "환경변수 SLACK_APP_TOKEN 가 placeholder 값입니다. "
            ".env 를 실제 토큰으로 채우세요."
        )

    return CoordinatorConfig(
        bot_token=bot_token,
        app_token=app_token,
        allowed_user_ids=_parse_allowed_ids(allowed_raw),
        log_level=log_level,
    )
