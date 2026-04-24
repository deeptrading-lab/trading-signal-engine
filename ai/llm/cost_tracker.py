"""
불변 CostTracker 클래스.

프로세스 수명 동안 LLM 호출의 누적 비용을 추적한다.
불변(frozen)이므로 직접 수정은 불가능하고, add() 메서드로 새 인스턴스를 반환한다.
"""

import sys
from dataclasses import dataclass
from typing import Optional
from .pricing import calculate_cost, Model


class BudgetExceededError(Exception):
    """예산을 초과할 때 발생하는 예외."""
    pass


# Python 3.10+ slots 지원, 3.9는 slots 제외
_dataclass_kwargs = {"frozen": True}
if sys.version_info >= (3, 10):
    _dataclass_kwargs["slots"] = True


@dataclass(**_dataclass_kwargs)
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
        usd: Optional[float] = None,
        model: Optional[Model] = None,
    ) -> "CostTracker":
        """새로운 토큰/비용을 추가하고 새 CostTracker 인스턴스를 반환한다.

        매개변수:
            input_tokens: 이번 호출의 입력 토큰 수.
            output_tokens: 이번 호출의 출력 토큰 수.
            usd: 이번 호출의 비용 (직접 지정). model과 함께 사용 불가.
            model: 이번 호출의 모델. usd와 함께 사용 불가. 모델 단가에 따라 자동 계산.

        반환값:
            새 CostTracker 인스턴스 (원본은 변경 없음).

        예외:
            BudgetExceededError: 누적 비용이 budget_usd를 초과할 때.
            ValueError: usd와 model을 동시에 지정할 때.
        """
        # usd와 model 둘 다 지정되면 오류
        if usd is not None and model is not None:
            raise ValueError("usd와 model을 동시에 지정할 수 없습니다.")

        # 비용 계산
        if usd is not None:
            cost = usd
        elif model is not None:
            cost = calculate_cost(model, input_tokens, output_tokens)
        else:
            raise ValueError("usd 또는 model 중 하나는 반드시 지정해야 합니다.")

        # 누적 비용 계산
        new_spent = self.usd_spent + cost

        # 예산 초과 확인 (strict >)
        if new_spent > self.budget_usd:
            raise BudgetExceededError(
                f"Budget exceeded: ${new_spent:.4f} > ${self.budget_usd:.4f}"
            )

        # 새 인스턴스 반환 (원본 불변)
        return CostTracker(
            input_tokens=self.input_tokens + input_tokens,
            output_tokens=self.output_tokens + output_tokens,
            usd_spent=new_spent,
            budget_usd=self.budget_usd,
        )
