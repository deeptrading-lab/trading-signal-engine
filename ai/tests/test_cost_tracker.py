"""비용 추적기 테스트 (AC-C)."""

import pytest
from dataclasses import FrozenInstanceError
from ai.llm import CostTracker, BudgetExceededError, Model


class TestCostTracker:
    """CostTracker 클래스의 불변성·비용 추적 테스트."""

    # AC-C1: 불변성 (add 호출 후 원본 불변, 새 인스턴스에만 변경)
    def test_cost_tracker_immutability(self):
        """AC-C1: add() 호출 후 원본은 변경되지 않음."""
        original = CostTracker(budget_usd=1.0)
        assert original.usd_spent == 0.0

        new_tracker = original.add(input_tokens=1000, output_tokens=500, usd=0.4)

        # 원본 변경 없음
        assert original.usd_spent == 0.0
        # 새 인스턴스에만 반영
        assert new_tracker.usd_spent == 0.4
        assert new_tracker.input_tokens == 1000
        assert new_tracker.output_tokens == 500

    # AC-C2: 예산 초과 시 BudgetExceededError
    def test_cost_tracker_budget_exceeded(self):
        """AC-C2: 누적 비용 > 예산 시 BudgetExceededError 발생."""
        tracker = CostTracker(budget_usd=1.0)
        with pytest.raises(BudgetExceededError):
            tracker.add(input_tokens=1000, output_tokens=1000, usd=1.1)

    # AC-C3: 예산과 정확히 같으면 성공 (strict >)
    def test_cost_tracker_budget_exact_match(self):
        """AC-C3: 누적 비용 == 예산일 때 성공."""
        tracker = CostTracker(budget_usd=1.0)
        new_tracker = tracker.add(input_tokens=1000, output_tokens=500, usd=1.0)
        assert new_tracker.usd_spent == 1.0

    # AC-C4: frozen=True이므로 직접 속성 대입 불가
    def test_cost_tracker_frozen(self):
        """AC-C4: frozen=True로 인해 속성 대입 시 FrozenInstanceError 발생."""
        tracker = CostTracker(budget_usd=1.0)
        with pytest.raises(FrozenInstanceError):
            tracker.usd_spent = 99  # type: ignore

    # AC-C5: __slots__으로 새 속성 추가 불가
    def test_cost_tracker_slots(self):
        """AC-C5: __slots__ 사용으로 새 속성 추가 시 AttributeError 발생."""
        tracker = CostTracker(budget_usd=1.0)
        with pytest.raises(AttributeError):
            tracker.new_attribute = "should fail"  # type: ignore

    # 추가: 모델 기반 비용 계산
    def test_cost_tracker_model_based_pricing(self):
        """모델을 지정한 경우 단가 테이블에서 자동 계산."""
        tracker = CostTracker(budget_usd=10.0)
        # HAIKU: input $1/M, output $5/M
        # 1000 input tokens = 1000/1M * $1 = $0.001
        # 500 output tokens = 500/1M * $5 = $0.0025
        # total = $0.0035
        new_tracker = tracker.add(input_tokens=1000, output_tokens=500, model=Model.HAIKU)
        assert new_tracker.usd_spent == pytest.approx(0.0035, abs=1e-6)

    def test_cost_tracker_sonnet_pricing(self):
        """SONNET 모델 기반 비용 계산."""
        tracker = CostTracker(budget_usd=10.0)
        # SONNET: input $3/M, output $15/M
        # 1000 input = $0.003, 500 output = $0.0075
        # total = $0.0105
        new_tracker = tracker.add(input_tokens=1000, output_tokens=500, model=Model.SONNET)
        assert new_tracker.usd_spent == pytest.approx(0.0105, abs=1e-6)

    def test_cost_tracker_cumulative(self):
        """누적 비용 추적."""
        tracker = CostTracker(budget_usd=10.0)
        tracker = tracker.add(input_tokens=1000, output_tokens=500, usd=0.5)
        assert tracker.usd_spent == pytest.approx(0.5, abs=1e-6)

        tracker = tracker.add(input_tokens=2000, output_tokens=1000, usd=0.3)
        assert tracker.usd_spent == pytest.approx(0.8, abs=1e-6)

        tracker = tracker.add(input_tokens=500, output_tokens=250, usd=0.15)
        assert tracker.usd_spent == pytest.approx(0.95, abs=1e-6)

    def test_cost_tracker_cannot_mix_usd_and_model(self):
        """usd와 model을 동시에 지정 불가."""
        tracker = CostTracker(budget_usd=10.0)
        with pytest.raises(ValueError):
            tracker.add(input_tokens=1000, output_tokens=500, usd=0.5, model=Model.HAIKU)

    def test_cost_tracker_must_specify_usd_or_model(self):
        """usd 또는 model 중 하나는 반드시 지정."""
        tracker = CostTracker(budget_usd=10.0)
        with pytest.raises(ValueError):
            tracker.add(input_tokens=1000, output_tokens=500)

    def test_cost_tracker_budget_validation_boundary(self):
        """예산 경계값 테스트."""
        tracker = CostTracker(budget_usd=1.0)

        # 0.99 추가: 성공
        new = tracker.add(input_tokens=0, output_tokens=0, usd=0.99)
        assert new.usd_spent == 0.99

        # 0.01 추가: 성공 (정확히 1.0)
        new = new.add(input_tokens=0, output_tokens=0, usd=0.01)
        assert new.usd_spent == 1.0

        # 0.001 추가: 실패 (1.001 > 1.0)
        with pytest.raises(BudgetExceededError):
            new.add(input_tokens=0, output_tokens=0, usd=0.001)
