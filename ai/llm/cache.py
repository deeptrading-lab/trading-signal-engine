"""
프롬프트 캐싱 헬퍼.

Anthropic SDK 메시지 포맷에 cache_control을 부착한다.
1,000자 이상 system prompt는 자동으로 ephemeral 캐싱 설정을 받는다.
"""

from typing import Any


# 캐싱 임계 길이 (문자)
CACHE_CONTROL_THRESHOLD_CHARS = 1_000


def build_system_block(text: str) -> list[dict[str, Any]]:
    """System prompt를 Anthropic Messages API 형식으로 변환하고, 필요시 cache_control을 부착한다.

    매개변수:
        text: System prompt 텍스트.

    반환값:
        Anthropic Messages API에 투입 가능한 메시지 블록 리스트.
        예: [{"type": "text", "text": "...", "cache_control": {"type": "ephemeral"}}]

    규칙:
        - text 길이가 CACHE_CONTROL_THRESHOLD_CHARS 이상이면 cache_control 부착.
        - 그 외는 cache_control 없음.
    """
    block: dict[str, Any] = {
        "type": "text",
        "text": text,
    }

    # 캐싱 조건: 길이 >= 임계치
    if len(text) >= CACHE_CONTROL_THRESHOLD_CHARS:
        block["cache_control"] = {"type": "ephemeral"}

    return [block]
