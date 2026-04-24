"""
LLM 모델 라우팅 로직.

텍스트 길이와 아이템 개수를 기준으로 최적의 모델을 선택한다.
결정적(deterministic)이며, 동일 입력에 대해 항상 동일 출력을 낸다.
"""

from typing import Optional
from .pricing import Model


# 라우팅 임계치
ROUTER_TEXT_LENGTH_THRESHOLD = 10_000  # 10,000자 이상 → SONNET
ROUTER_ITEM_COUNT_THRESHOLD = 30  # 30개 이상 → SONNET


def select_model(
    text_length: int,
    item_count: int,
    force: Optional[Model] = None,
) -> Model:
    """텍스트 길이와 아이템 개수를 보고 적절한 모델을 선택한다.

    매개변수:
        text_length: 입력 텍스트의 길이 (문자 단위).
        item_count: 처리할 아이템 개수.
        force: 강제 지정 모델. None이 아니면 임계치 무시하고 해당 모델 반환.

    반환값:
        선택된 모델 (Model enum).

    규칙:
        - force가 주어지면 우선적으로 반환.
        - text_length >= 10_000 또는 item_count >= 30 → SONNET
        - 그 외 → HAIKU
        (OPUS는 확장 포인트로만 enum에 존재)
    """
    # force 인자 우선
    if force is not None:
        return force

    # 임계치 기반 판단
    if text_length >= ROUTER_TEXT_LENGTH_THRESHOLD or item_count >= ROUTER_ITEM_COUNT_THRESHOLD:
        return Model.SONNET

    return Model.HAIKU
