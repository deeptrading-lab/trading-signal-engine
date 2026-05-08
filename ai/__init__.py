"""AI / Analysis 파이프라인 공개 API.

LLM API는 optional dependency가 필요하므로 top-level import 시 즉시 로딩하지 않는다.
이렇게 해야 비용 없는 분석 모듈(`ai.stock_signal`)을 SDK 설치 없이 실행할 수 있다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
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


def __getattr__(name: str) -> Any:
    if name not in __all__:
        raise AttributeError(f"module 'ai' has no attribute {name!r}")

    from . import llm

    return getattr(llm, name)
