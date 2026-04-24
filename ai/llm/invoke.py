"""
통합 LLM 호출 래퍼.

모델 라우팅, 캐싱, 재시도, 비용 추적을 한 곳에서 처리한다.

사용:
    tracker = CostTracker(budget_usd=10.0)
    response, tracker = invoke_llm(
        prompt="분석해줘",
        items=[...],
        tracker=tracker,
    )
    # response는 anthropic.Message
    # tracker는 새로운 CostTracker 인스턴스 (원본 변경 없음)
"""

import logging
from typing import Any, Optional, Tuple

from anthropic import Anthropic
from anthropic.types import Message

from .cache import build_system_block
from .cost_tracker import CostTracker
from .pricing import Model
from .retry import narrow_retry
from .router import select_model


logger = logging.getLogger(__name__)


def invoke_llm(
    prompt: str,
    items: list[Any],
    tracker: CostTracker,
    system_prompt: str = "",
    force: Optional[Model] = None,
    client: Optional[Anthropic] = None,
    **kwargs,
) -> Tuple[Message, CostTracker]:
    """통합 LLM 호출 래퍼.

    다음을 순서대로 실행한다:
    1. 모델 선택 (select_model)
    2. System prompt에 캐시 제어 부착 (build_system_block)
    3. 재시도 데코레이터 적용된 SDK 호출
    4. 응답 usage를 tracker.add()로 누적 (모델 단가 테이블 기반)
    5. 새 tracker 반환

    매개변수:
        prompt: 사용자 입력 (프롬프트).
        items: 처리할 아이템 리스트 (개수는 라우팅에 사용).
        tracker: 비용 추적기.
        system_prompt: System prompt (기본값 ""). 1000자 이상이면 캐싱 적용.
        force: 강제 모델 선택 (기본값 None).
        client: Anthropic SDK 클라이언트. None이면 내부에서 생성.
            테스트/설정 커스터마이즈 시 주입 (DI).
        **kwargs: Anthropic SDK의 messages.create()에 전달할 추가 인자.
            (max_tokens 등을 덮어쓸 수 있음; 미지정 시 기본값 2048)

    반환값:
        (response, new_tracker) 튜플.
        - response: anthropic.Message 인스턴스 (LLM 응답).
        - new_tracker: 새로운 CostTracker 인스턴스 (원본 변경 없음).

    예외:
        BudgetExceededError: 호출 후 누적 비용이 예산 초과.
        anthropic.APIError: SDK 예외 (재시도 가능한 것은 자동 재시도 후 전파).
    """
    # 1. 모델 선택
    selected_model = select_model(
        text_length=len(prompt),
        item_count=len(items),
        force=force,
    )

    # 2. System block 구성 (캐시 제어 자동 부착)
    # Anthropic Messages API messages 스펙: {"role": "user", "content": "..."}
    messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
    system_blocks: list[dict[str, Any]] = []
    if system_prompt:
        system_blocks = build_system_block(system_prompt)

    # 3. 클라이언트 주입(없으면 생성) + 재시도 데코레이터 적용 SDK 호출
    sdk_client = client if client is not None else Anthropic()

    # 사용자가 kwargs로 max_tokens 를 넘기면 충돌 방지(TypeError) 위해 setdefault 사용
    kwargs.setdefault("max_tokens", 2048)

    @narrow_retry
    def _call_api():
        return sdk_client.messages.create(
            model=selected_model.value,
            system=system_blocks if system_blocks else None,
            messages=messages,
            **kwargs,
        )

    response = _call_api()

    # 4. 비용 누적 (usage가 있으면 모델 단가로 계산)
    if response.usage is None:
        # SDK 응답에 usage가 없으면 비용을 추적할 수 없음. 조용히 넘기지 않고 경고 로깅.
        logger.warning(
            "SDK response missing usage; cost not tracked for this call "
            "(model=%s)",
            selected_model.value,
        )
        new_tracker = tracker
    else:
        new_tracker = tracker.add(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            usd=_compute_cost(
                selected_model,
                response.usage.input_tokens,
                response.usage.output_tokens,
            ),
        )

    # 5. 새 tracker와 response 반환
    return response, new_tracker


def _compute_cost(model: Model, input_tokens: int, output_tokens: int) -> float:
    """모델 단가 테이블 기반 비용(USD)을 계산한다.

    pricing.calculate_cost 를 얇게 위임한다. invoke_llm 에서만 쓰는 내부 헬퍼.
    """
    from .pricing import calculate_cost

    return calculate_cost(model, input_tokens, output_tokens)
