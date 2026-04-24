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

from typing import Optional, Any, Tuple
from anthropic import Anthropic
from anthropic.types import Message

from .pricing import Model
from .router import select_model
from .cache import build_system_block
from .retry import narrow_retry
from .cost_tracker import CostTracker


# 글로벌 SDK 인스턴스 (필요시 재설정 가능)
_client: Optional[Anthropic] = None


def set_client(client: Anthropic) -> None:
    """테스트 또는 커스텀 설정용 SDK 클라이언트를 지정한다.

    매개변수:
        client: Anthropic 인스턴스.
    """
    global _client
    _client = client


def get_client() -> Anthropic:
    """SDK 클라이언트를 반환한다 (없으면 생성).

    반환값:
        Anthropic 인스턴스.
    """
    global _client
    if _client is None:
        _client = Anthropic()
    return _client


def invoke_llm(
    prompt: str,
    items: list[Any],
    tracker: CostTracker,
    system_prompt: str = "",
    force: Optional[Model] = None,
    **kwargs,
) -> Tuple[Message, CostTracker]:
    """통합 LLM 호출 래퍼.

    다음을 순서대로 실행한다:
    1. 모델 선택 (select_model)
    2. System prompt에 캐시 제어 부착 (build_system_block)
    3. 재시도 데코레이터 적용된 SDK 호출
    4. 응답 usage를 tracker.add()로 누적
    5. 새 tracker 반환

    매개변수:
        prompt: 사용자 입력 (프롬프트).
        items: 처리할 아이템 리스트 (개수는 라우팅에 사용).
        tracker: 비용 추적기.
        system_prompt: System prompt (기본값 ""). 1000자 이상이면 캐싱 적용.
        force: 강제 모델 선택 (기본값 None).
        **kwargs: Anthropic SDK의 messages.create()에 전달할 추가 인자.

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
    messages: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    system_blocks = []
    if system_prompt:
        system_blocks = build_system_block(system_prompt)

    # 3. 모델별 API 엔드포인트 및 재시도 데코레이터 적용
    client = get_client()

    @narrow_retry
    def _call_api():
        return client.messages.create(
            model=selected_model.value,
            max_tokens=2048,
            system=system_blocks if system_blocks else None,
            messages=messages,
            **kwargs,
        )

    response = _call_api()

    # 4. 비용 누적
    if response.usage:
        new_tracker = tracker.add(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            model=selected_model,
        )
    else:
        # Usage 정보가 없으면 추적 건너뜀
        new_tracker = tracker

    # 5. 새 tracker와 response 반환
    return response, new_tracker
