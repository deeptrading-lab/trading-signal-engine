"""모델 라우팅 테스트 (AC-R)."""

import pytest
from ai.llm import Model, select_model


class TestRouter:
    """select_model() 함수의 라우팅 로직 테스트."""

    # AC-R1: text_length >= 10_000 → SONNET
    def test_router_sonnet_by_text_length(self):
        """AC-R1: text_length >= 10_000일 때 SONNET 선택."""
        result = select_model(text_length=10_000, item_count=0)
        assert result == Model.SONNET

    # AC-R2: text_length < 10_000, item_count < 30 → HAIKU
    def test_router_haiku_below_threshold(self):
        """AC-R2: 모든 임계치 미만일 때 HAIKU 선택."""
        result = select_model(text_length=9_999, item_count=29)
        assert result == Model.HAIKU

    # AC-R3: item_count >= 30 → SONNET
    def test_router_sonnet_by_item_count(self):
        """AC-R3: item_count >= 30일 때 SONNET 선택."""
        result = select_model(text_length=0, item_count=30)
        assert result == Model.SONNET

    # AC-R4: item_count < 30, text_length < 10_000 → HAIKU
    def test_router_haiku_by_item_count_below(self):
        """AC-R4: item_count < 30일 때 HAIKU 선택."""
        result = select_model(text_length=0, item_count=29)
        assert result == Model.HAIKU

    # AC-R5: force 인자 우선
    def test_router_force_overrides_threshold(self):
        """AC-R5: force 인자가 임계치를 우선."""
        result = select_model(text_length=50_000, item_count=100, force=Model.HAIKU)
        assert result == Model.HAIKU

    # AC-R6: 결정적(deterministic) 동작
    def test_router_deterministic(self):
        """AC-R6: 동일 입력에 대해 항상 동일 출력."""
        inputs = [
            (5_000, 10, None),
            (10_000, 0, None),
            (0, 30, None),
            (50_000, 100, Model.HAIKU),
        ]

        for text_length, item_count, force in inputs:
            result1 = select_model(text_length, item_count, force)
            result2 = select_model(text_length, item_count, force)
            result3 = select_model(text_length, item_count, force)
            assert result1 == result2 == result3

    # 경계 케이스
    def test_router_boundary_text_length(self):
        """text_length의 경계값 테스트."""
        assert select_model(10_000, 0) == Model.SONNET
        assert select_model(9_999, 0) == Model.HAIKU
        assert select_model(10_001, 0) == Model.SONNET

    def test_router_boundary_item_count(self):
        """item_count의 경계값 테스트."""
        assert select_model(0, 30) == Model.SONNET
        assert select_model(0, 29) == Model.HAIKU
        assert select_model(0, 31) == Model.SONNET

    def test_router_force_with_haiku(self):
        """force=HAIKU인 경우."""
        result = select_model(50_000, 100, force=Model.HAIKU)
        assert result == Model.HAIKU

    def test_router_force_with_sonnet(self):
        """force=SONNET인 경우."""
        result = select_model(100, 1, force=Model.SONNET)
        assert result == Model.SONNET

    def test_router_force_with_opus(self):
        """force=OPUS인 경우 (확장 포인트)."""
        result = select_model(100, 1, force=Model.OPUS)
        assert result == Model.OPUS
