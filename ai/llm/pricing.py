"""
LLM 모델별 단가 테이블 (2026-04-25 기준, Anthropic 공식 가격).

프롬프트 캐싱 hit 시 입력 비용 할인은 근사치로만 계산 (정확한 캐시 write/read 분리는 후속 과제).
"""

from enum import Enum
from dataclasses import dataclass


class Model(str, Enum):
    """지원하는 LLM 모델 식별자."""
    HAIKU = "haiku"
    SONNET = "sonnet"
    OPUS = "opus"  # 확장 포인트: 실제 라우팅은 구현되지 않음


@dataclass(frozen=True)
class PricingInfo:
    """모델 단가 정보."""
    input_usd_per_million: float
    output_usd_per_million: float


# 모델별 단가 테이블 (2026-04-25 기준)
PRICING_TABLE = {
    Model.HAIKU: PricingInfo(input_usd_per_million=1.00, output_usd_per_million=5.00),
    Model.SONNET: PricingInfo(input_usd_per_million=3.00, output_usd_per_million=15.00),
    Model.OPUS: PricingInfo(input_usd_per_million=5.00, output_usd_per_million=25.00),
}


def get_pricing(model: Model) -> PricingInfo:
    """주어진 모델의 단가 정보를 반환한다.

    Args:
        model: 모델 식별자 (Model enum).

    Returns:
        해당 모델의 PricingInfo.

    Raises:
        ValueError: 지원하지 않는 모델.
    """
    if model not in PRICING_TABLE:
        raise ValueError(f"Unsupported model: {model}")
    return PRICING_TABLE[model]


def calculate_cost(model: Model, input_tokens: int, output_tokens: int) -> float:
    """입출력 토큰 수와 모델명으로부터 비용(USD)을 계산한다.

    Args:
        model: 모델 식별자.
        input_tokens: 입력 토큰 수.
        output_tokens: 출력 토큰 수.

    Returns:
        계산된 비용 (USD, float).
    """
    pricing = get_pricing(model)
    input_cost = (input_tokens / 1_000_000) * pricing.input_usd_per_million
    output_cost = (output_tokens / 1_000_000) * pricing.output_usd_per_million
    return input_cost + output_cost
