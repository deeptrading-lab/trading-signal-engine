"""비용 추적기 테스트 (AC-C)."""

from dataclasses import FrozenInstanceError

import pytest

from ai.llm import BudgetExceededError, CostTracker, Model
from ai.llm.cost_tracker import CostTracker as CostTrackerCls  # from_usage 사용용


class TestCostTracker:
    """CostTracker 클래스의 불변성·비용 추적 테스트."""

    # AC-C1: 불변성 (add 호출 후 원본 불변, 새 인스턴스에만 반영)
    def test_cost_tracker_immutability(self):
        """AC-C1: add() 호출 후 원본은 변경되지 않음."""
        original = CostTracker(budget_usd=1.0)
        assert original.usd_spent == 0.0

        new_tracker = original.add(input_tokens=1000, output_tokens=500, usd=0.4)

        # 원본 불변
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
            tracker.usd_spent = 99  # type: ignore[misc]

    # AC-C5: __slots__로 새 속성 추가 불가
    def test_cost_tracker_slots(self):
        """AC-C5: __slots__ 사용으로 새 속성 추가 시 속성 차단 예외 발생.

        PRD 문언은 AttributeError 지만 Python 3.11 `@dataclass(frozen=True, slots=True)`
        조합에서는 알려진 버그로 zero-arg `super()` 참조 실패가 먼저 일어나 TypeError
        가 발생한다(속성 이름이 slots 에 없기 때문에 frozen __setattr__ 본문이 실행됨).
        기능적 본질("새 속성 추가가 차단됨")을 검증하도록 두 예외 모두 허용.
        """
        tracker = CostTracker(budget_usd=1.0)
        with pytest.raises((AttributeError, TypeError)):
            tracker.new_attribute = "should fail"  # type: ignore[attr-defined]

    def test_cost_tracker_has_slots(self):
        """__slots__ 정의 자체를 별도로 검증 (AC-C5 보강)."""
        assert hasattr(CostTracker, "__slots__")
        assert "input_tokens" in CostTracker.__slots__
        assert "output_tokens" in CostTracker.__slots__
        assert "usd_spent" in CostTracker.__slots__
        assert "budget_usd" in CostTracker.__slots__

    # add() 엄격 시그니처: usd 필수 키워드 인자
    def test_cost_tracker_add_requires_usd_keyword(self):
        """add()는 usd 키워드 인자를 필수로 받는다(PRD 엄격 시그니처)."""
        tracker = CostTracker(budget_usd=1.0)
        with pytest.raises(TypeError):
            # usd 누락 → TypeError
            tracker.add(input_tokens=100, output_tokens=50)  # type: ignore[call-arg]

    # from_usage 팩토리: 모델 단가 기반 자동 계산
    def test_cost_tracker_from_usage_haiku(self):
        """from_usage(): HAIKU 단가로 자동 계산."""
        tracker = CostTracker(budget_usd=10.0)
        # HAIKU: 1000 input * $1/M + 500 output * $5/M = 0.0035
        new_tracker = CostTrackerCls.from_usage(
            tracker, Model.HAIKU, input_tokens=1000, output_tokens=500
        )
        assert new_tracker.usd_spent == pytest.approx(0.0035, abs=1e-6)
        assert new_tracker.input_tokens == 1000
        assert new_tracker.output_tokens == 500

    def test_cost_tracker_from_usage_sonnet(self):
        """from_usage(): SONNET 단가로 자동 계산."""
        tracker = CostTracker(budget_usd=10.0)
        # SONNET: 1000 input * $3/M + 500 output * $15/M = 0.0105
        new_tracker = CostTrackerCls.from_usage(
            tracker, Model.SONNET, input_tokens=1000, output_tokens=500
        )
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
