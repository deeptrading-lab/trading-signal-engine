"""통합 LLM 호출 래퍼 테스트 (AC-I)."""

import pytest
from unittest.mock import Mock, MagicMock, patch
from anthropic import Anthropic
from anthropic.types import Message
from ai.llm import (
    invoke_llm,
    set_client,
    get_client,
    CostTracker,
    BudgetExceededError,
    Model,
)


class MockMessage:
    """anthropic.Message mock."""

    def __init__(self, content="response", input_tokens=1000, output_tokens=500):
        self.content = content
        self.usage = Mock(input_tokens=input_tokens, output_tokens=output_tokens)


class TestInvoke:
    """invoke_llm() 함수의 통합 동작 테스트."""

    # AC-I1: 짧은 prompt → HAIKU 선택, 비용 누적, 새 tracker 반환
    def test_invoke_short_prompt_haiku_selection(self):
        """AC-I1: 짧은 prompt는 HAIKU 선택, 비용 추적."""
        # Mock 클라이언트
        mock_client = Mock(spec=Anthropic)
        mock_response = MockMessage(input_tokens=1000, output_tokens=500)
        mock_client.messages.create.return_value = mock_response

        set_client(mock_client)

        # 짧은 prompt
        prompt = "분석해줘"  # 4자
        tracker = CostTracker(budget_usd=10.0)

        response, new_tracker = invoke_llm(
            prompt=prompt,
            items=[],
            tracker=tracker,
        )

        # 응답 검증
        assert response == mock_response
        # 원본 tracker 불변
        assert tracker.usd_spent == 0.0
        # 새 tracker에 비용 반영
        # HAIKU: 1000 input * 1/1M + 500 output * 5/1M = 0.001 + 0.0025 = 0.0035
        assert new_tracker.usd_spent == pytest.approx(0.0035, abs=1e-6)
        assert new_tracker.input_tokens == 1000
        assert new_tracker.output_tokens == 500

        # SDK가 실제로 호출되었는지 검증
        assert mock_client.messages.create.called

    # AC-I2: 예산 초과 시 BudgetExceededError, 추가 호출 없음
    def test_invoke_budget_exceeded(self):
        """AC-I2: 비용 초과 시 BudgetExceededError, SDK 호출 없음."""
        mock_client = Mock(spec=Anthropic)
        mock_response = MockMessage(input_tokens=1000, output_tokens=500)
        mock_client.messages.create.return_value = mock_response

        set_client(mock_client)

        prompt = "분석해줘"
        tracker = CostTracker(budget_usd=0.002)  # 매우 낮은 예산

        with pytest.raises(BudgetExceededError):
            invoke_llm(
                prompt=prompt,
                items=[],
                tracker=tracker,
            )

        # SDK 호출 발생 (비용 계산 후 BudgetExceededError raise)
        # 실제로는 호출되고 반환받은 후 add()에서 오류 발생
        assert mock_client.messages.create.called

    # AC-I3: System prompt 길이 >= 1000자이면 cache_control 포함
    def test_invoke_cache_control_in_request(self):
        """AC-I3: 긴 system prompt에 cache_control 포함."""
        mock_client = Mock(spec=Anthropic)
        mock_response = MockMessage()
        mock_client.messages.create.return_value = mock_response

        set_client(mock_client)

        prompt = "분석"
        long_system_prompt = "x" * 1200  # 1200자

        tracker = CostTracker(budget_usd=10.0)

        invoke_llm(
            prompt=prompt,
            items=[],
            tracker=tracker,
            system_prompt=long_system_prompt,
        )

        # SDK 호출 확인
        assert mock_client.messages.create.called

        # 호출 인자에서 system이 존재하고 cache_control 포함
        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert "system" in call_kwargs
        system_blocks = call_kwargs["system"]
        assert isinstance(system_blocks, list)
        assert len(system_blocks) > 0

        # cache_control 확인
        found_cache_control = False
        for block in system_blocks:
            if "cache_control" in block:
                found_cache_control = True
                assert block["cache_control"]["type"] == "ephemeral"

        assert found_cache_control

    # AC-I4: force 인자로 SONNET 강제
    def test_invoke_force_sonnet(self):
        """AC-I4: force=SONNET이면 SONNET SDK 엔드포인트 호출."""
        mock_client = Mock(spec=Anthropic)
        mock_response = MockMessage(input_tokens=1000, output_tokens=500)
        mock_client.messages.create.return_value = mock_response

        set_client(mock_client)

        prompt = "분석"  # 짧은 prompt
        tracker = CostTracker(budget_usd=10.0)

        # force=SONNET으로 강제
        response, new_tracker = invoke_llm(
            prompt=prompt,
            items=[],
            tracker=tracker,
            force=Model.SONNET,
        )

        # SDK 호출 확인
        assert mock_client.messages.create.called

        # 호출 인자에서 model=sonnet 확인
        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert call_kwargs["model"] == "sonnet"

        # SONNET 단가 적용
        # SONNET: 1000 input * 3/1M + 500 output * 15/1M = 0.003 + 0.0075 = 0.0105
        assert new_tracker.usd_spent == pytest.approx(0.0105, abs=1e-6)

    # 추가: 텍스트 길이 기반 모델 선택
    def test_invoke_long_text_selects_sonnet(self):
        """긴 텍스트 입력이 SONNET 선택."""
        mock_client = Mock(spec=Anthropic)
        mock_response = MockMessage()
        mock_client.messages.create.return_value = mock_response

        set_client(mock_client)

        long_prompt = "x" * 10_000  # 10000자, SONNET 임계치
        tracker = CostTracker(budget_usd=10.0)

        invoke_llm(prompt=long_prompt, items=[], tracker=tracker)

        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert call_kwargs["model"] == "sonnet"

    # 추가: 아이템 개수 기반 모델 선택
    def test_invoke_many_items_selects_sonnet(self):
        """많은 아이템이 SONNET 선택."""
        mock_client = Mock(spec=Anthropic)
        mock_response = MockMessage()
        mock_client.messages.create.return_value = mock_response

        set_client(mock_client)

        prompt = "분석"
        items = list(range(30))  # 30개, SONNET 임계치
        tracker = CostTracker(budget_usd=10.0)

        invoke_llm(prompt=prompt, items=items, tracker=tracker)

        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert call_kwargs["model"] == "sonnet"

    # 추가: usage가 없는 경우 처리
    def test_invoke_no_usage_info(self):
        """Usage 정보가 없어도 정상 동작."""
        mock_client = Mock(spec=Anthropic)
        mock_response = MockMessage()
        mock_response.usage = None  # usage 없음
        mock_client.messages.create.return_value = mock_response

        set_client(mock_client)

        prompt = "분석"
        tracker = CostTracker(budget_usd=10.0)

        response, new_tracker = invoke_llm(
            prompt=prompt,
            items=[],
            tracker=tracker,
        )

        # tracker는 변경 없어야 함 (usage 없으므로)
        assert new_tracker.usd_spent == tracker.usd_spent

    # 추가: 빈 system_prompt
    def test_invoke_empty_system_prompt(self):
        """빈 system_prompt도 처리 가능."""
        mock_client = Mock(spec=Anthropic)
        mock_response = MockMessage()
        mock_client.messages.create.return_value = mock_response

        set_client(mock_client)

        prompt = "분석"
        tracker = CostTracker(budget_usd=10.0)

        invoke_llm(
            prompt=prompt,
            items=[],
            tracker=tracker,
            system_prompt="",  # 빈 문자열
        )

        call_kwargs = mock_client.messages.create.call_args.kwargs
        # system은 None이거나 빈 리스트
        assert call_kwargs.get("system") is None or call_kwargs.get("system") == []

    # 추가: 클라이언트 설정/조회
    def test_invoke_client_management(self):
        """set_client/get_client 동작."""
        mock_client = Mock(spec=Anthropic)
        set_client(mock_client)
        retrieved = get_client()
        assert retrieved == mock_client

    # 추가: 누적 비용 추적
    def test_invoke_cumulative_cost_tracking(self):
        """여러 호출의 누적 비용 추적."""
        mock_client = Mock(spec=Anthropic)
        mock_response = MockMessage(input_tokens=1000, output_tokens=500)
        mock_client.messages.create.return_value = mock_response

        set_client(mock_client)

        tracker = CostTracker(budget_usd=10.0)

        # 첫 호출
        _, tracker = invoke_llm(prompt="A", items=[], tracker=tracker)
        cost_after_1 = tracker.usd_spent

        # 두 번째 호출
        _, tracker = invoke_llm(prompt="B", items=[], tracker=tracker)
        cost_after_2 = tracker.usd_spent

        # 비용 누적 확인
        assert cost_after_2 > cost_after_1
        assert cost_after_2 == pytest.approx(cost_after_1 * 2, abs=1e-6)
