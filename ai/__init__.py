"""
AI / Analysis 파이프라인 (Python).

LLM 비용 가드, 신호 분석, LangGraph 오케스트레이션을 포함한다.

공개 API 정책:
- 이 모듈(`ai`)에서는 **사용자 레벨 API**(래퍼·도메인 엔티티·에러)만 재노출한다.
- 세부 단가 테이블 · 재시도 내부 상수 등 **내부 구성 요소**는 `ai.llm` 하위 모듈에서
  직접 import 한다(예: `from ai.llm import PRICING_TABLE`).
- 사용자 레벨 API 선정 기준:
    1. LLM 호출 래퍼 (`invoke_llm`, `narrow_retry`, `build_system_block`)
    2. 모델/비용 엔티티 (`Model`, `CostTracker`)
    3. 외부로 전파되는 예외 (`BudgetExceededError`)
    4. 라우팅 결정 함수 (`select_model`)
"""

from .llm import (
    BudgetExceededError,
    CostTracker,
    Model,
    build_system_block,
    invoke_llm,
    narrow_retry,
    select_model,
)


__all__ = [
    "Model",
    "CostTracker",
    "BudgetExceededError",
    "select_model",
    "invoke_llm",
    "narrow_retry",
    "build_system_block",
]
