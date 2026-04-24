"""
불변 CostTracker 클래스.

프로세스 수명 동안 LLM 호출의 누적 비용을 추적한다.
불변(frozen)이므로 직접 수정은 불가능하고, add() 메서드로 새 인스턴스를 반환한다.

PRD §6 "Python 3.11+" 제약에 따라 `@dataclass(frozen=True, slots=True)` 단일 경로로
구성한다. 모델 단가 기반 자동 계산이 필요하면 `from_usage()` 팩토리 헬퍼를 쓰라.
"""

from dataclasses import dataclass

from .pricing import Model, calculate_cost


class BudgetExceededError(Exception):
    """예산을 초과할 때 발생하는 예외."""

    pass


@dataclass(frozen=True, slots=True)
class CostTracker:
    """LLM 호출 비용 누적 추적기.

    불변(frozen=True)이므로 인스턴스 속성을 직접 변경할 수 없다.
    add() 메서드는 새 CostTracker 인스턴스를 반환한다.
    """

    input_tokens: int = 0
    """누적 입력 토큰 수."""

    output_tokens: int = 0
    """누적 출력 토큰 수."""

    usd_spent: float = 0.0
    """누적 지출 (USD)."""

    budget_usd: float = 100.0
    """하루 예산 한도 (USD). 기본값 $100."""

    def add(
        self,
        *,
        input_tokens: int,
        output_tokens: int,
        usd: float,
    ) -> "CostTracker":
        """새로운 토큰/비용을 추가하고 새 CostTracker 인스턴스를 반환한다.

        PRD 시그니처에 맞춰 `usd`를 필수 인자로 받는다. 모델 단가에서 자동 계산이
        필요하면 `CostTracker.from_usage(...)` 를 사용하라.

        매개변수:
            input_tokens: 이번 호출의 입력 토큰 수.
            output_tokens: 이번 호출의 출력 토큰 수.
            usd: 이번 호출의 비용 (USD).

        반환값:
            새 CostTracker 인스턴스 (원본은 변경 없음).

        예외:
            BudgetExceededError: 누적 비용이 budget_usd를 strict로 초과할 때.
        """
        new_spent = self.usd_spent + usd

        # 예산 초과 확인 (strict >; 경계값 == 은 허용)
        if new_spent > self.budget_usd:
            raise BudgetExceededError(
                f"Budget exceeded: ${new_spent:.4f} > ${self.budget_usd:.4f}"
            )

        return CostTracker(
            input_tokens=self.input_tokens + input_tokens,
            output_tokens=self.output_tokens + output_tokens,
            usd_spent=new_spent,
            budget_usd=self.budget_usd,
        )

    @classmethod
    def from_usage(
        cls,
        tracker: "CostTracker",
        model: Model,
        input_tokens: int,
        output_tokens: int,
    ) -> "CostTracker":
        """모델 단가 테이블로부터 비용을 계산해 tracker 에 누적한 새 인스턴스를 반환.

        PRD `add()` 시그니처(엄격한 usd 필수)를 유지하면서, 모델 단가 기반 자동 계산
        흐름이 필요한 호출자를 위한 보조 팩토리.

        매개변수:
            tracker: 기준 CostTracker.
            model: 사용한 모델 식별자.
            input_tokens: 이번 호출의 입력 토큰 수.
            output_tokens: 이번 호출의 출력 토큰 수.

        반환값:
            새 CostTracker 인스턴스.
        """
        cost = calculate_cost(model, input_tokens, output_tokens)
        return tracker.add(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            usd=cost,
        )
