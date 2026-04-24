"""모델 단가 테이블 및 비용 계산 테스트."""

import pytest
from ai.llm import Model, PricingInfo, PRICING_TABLE, get_pricing, calculate_cost


class TestPricing:
    """단가 테이블 및 비용 계산 테스트."""

    def test_pricing_table_exists(self):
        """단가 테이블이 필수 모델을 포함."""
        assert Model.HAIKU in PRICING_TABLE
        assert Model.SONNET in PRICING_TABLE
        assert Model.OPUS in PRICING_TABLE

    def test_pricing_info_structure(self):
        """PricingInfo 구조."""
        info = PRICING_TABLE[Model.HAIKU]
        assert isinstance(info, PricingInfo)
        assert info.input_usd_per_million == 1.0
        assert info.output_usd_per_million == 5.0

    def test_get_pricing_haiku(self):
        """HAIKU 단가 조회."""
        pricing = get_pricing(Model.HAIKU)
        assert pricing.input_usd_per_million == 1.0
        assert pricing.output_usd_per_million == 5.0

    def test_get_pricing_sonnet(self):
        """SONNET 단가 조회."""
        pricing = get_pricing(Model.SONNET)
        assert pricing.input_usd_per_million == 3.0
        assert pricing.output_usd_per_million == 15.0

    def test_get_pricing_opus(self):
        """OPUS 단가 조회."""
        pricing = get_pricing(Model.OPUS)
        assert pricing.input_usd_per_million == 5.0
        assert pricing.output_usd_per_million == 25.0

    def test_get_pricing_invalid_model(self):
        """지원하지 않는 모델 조회 시 ValueError."""
        with pytest.raises(ValueError):
            get_pricing("invalid_model")  # type: ignore

    def test_calculate_cost_haiku(self):
        """HAIKU 비용 계산."""
        # 1M input tokens = $1.0, 1M output tokens = $5.0
        # 1000 input = $0.001, 500 output = $0.0025
        cost = calculate_cost(Model.HAIKU, 1000, 500)
        assert cost == pytest.approx(0.0035, abs=1e-6)

    def test_calculate_cost_sonnet(self):
        """SONNET 비용 계산."""
        # 1M input tokens = $3.0, 1M output tokens = $15.0
        # 1000 input = $0.003, 500 output = $0.0075
        cost = calculate_cost(Model.SONNET, 1000, 500)
        assert cost == pytest.approx(0.0105, abs=1e-6)

    def test_calculate_cost_opus(self):
        """OPUS 비용 계산."""
        # 1M input tokens = $5.0, 1M output tokens = $25.0
        # 1000 input = $0.005, 500 output = $0.0125
        cost = calculate_cost(Model.OPUS, 1000, 500)
        assert cost == pytest.approx(0.0175, abs=1e-6)

    def test_calculate_cost_zero_tokens(self):
        """0 토큰 비용."""
        cost = calculate_cost(Model.HAIKU, 0, 0)
        assert cost == 0.0

    def test_calculate_cost_million_tokens(self):
        """1M 토큰 비용."""
        cost = calculate_cost(Model.HAIKU, 1_000_000, 1_000_000)
        assert cost == pytest.approx(1.0 + 5.0, abs=1e-6)

    def test_calculate_cost_large_tokens(self):
        """대량 토큰 비용."""
        cost = calculate_cost(Model.SONNET, 10_000_000, 5_000_000)
        # input: 10M * 3/1M = $30, output: 5M * 15/1M = $75
        assert cost == pytest.approx(105.0, abs=1e-6)

    def test_pricing_table_2026_04_values(self):
        """2026-04-25 기준 정확한 단가."""
        # PRD에 지정된 정확한 값
        assert PRICING_TABLE[Model.HAIKU].input_usd_per_million == 1.00
        assert PRICING_TABLE[Model.HAIKU].output_usd_per_million == 5.00

        assert PRICING_TABLE[Model.SONNET].input_usd_per_million == 3.00
        assert PRICING_TABLE[Model.SONNET].output_usd_per_million == 15.00

        assert PRICING_TABLE[Model.OPUS].input_usd_per_million == 5.00
        assert PRICING_TABLE[Model.OPUS].output_usd_per_million == 25.00
