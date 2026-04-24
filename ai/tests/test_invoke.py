"""통합 LLM 호출 래퍼 테스트 (AC-I).

모든 테스트는 Anthropic SDK 클라이언트를 **DI(주입)** 방식으로 넘긴다. 전역 상태
(`_client` / `set_client` / `get_client`)는 제거되었다.
"""

from unittest.mock import Mock

import pytest
from anthropic import Anthropic

from ai.llm import (
    BudgetExceededError,
    CostTracker,
    Model,
    invoke_llm,
)


class MockMessage:
    """anthropic.Message mock."""

    def __init__(self, content="response", input_tokens=1000, output_tokens=500):
        self.content = content
        self.usage = Mock(input_tokens=input_tokens, output_tokens=output_tokens)


def _make_mock_client(response: MockMessage) -> Mock:
    client = Mock(spec=Anthropic)
    client.messages.create.return_value = response
    return client


class TestInvoke:
    """invoke_llm() 함수의 통합 동작 테스트."""

    # AC-I1: 짧은 prompt → HAIKU 선택, 비용 누적, 새 tracker 반환
    def test_invoke_short_prompt_haiku_selection(self):
        """AC-I1: 짧은 prompt는 HAIKU 선택, 비용 추적."""
        mock_response = MockMessage(input_tokens=1000, output_tokens=500)
        mock_client = _make_mock_client(mock_response)

        prompt = "분석해줘"  # 4자
        tracker = CostTracker(budget_usd=10.0)

        response, new_tracker = invoke_llm(
            prompt=prompt,
            items=[],
            tracker=tracker,
            client=mock_client,
        )

        # 응답 검증
        assert response is mock_response
        # 원본 tracker 불변
        assert tracker.usd_spent == 0.0
        # HAIKU: 1000 input * $1/M + 500 output * $5/M = 0.001 + 0.0025 = 0.0035
        assert new_tracker.usd_spent == pytest.approx(0.0035, abs=1e-6)
        assert new_tracker.input_tokens == 1000
        assert new_tracker.output_tokens == 500

        # SDK 호출 검증
        assert mock_client.messages.create.called
        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert call_kwargs["model"] == "haiku"
        # M5: messages 페이로드 스펙 - role/content 형식
        assert call_kwargs["messages"] == [{"role": "user", "content": prompt}]

    # AC-I2: 예산 초과 시 BudgetExceededError
    def test_invoke_budget_exceeded(self):
        """AC-I2: 비용 초과 시 BudgetExceededError raise."""
        mock_response = MockMessage(input_tokens=1000, output_tokens=500)
        mock_client = _make_mock_client(mock_response)

        prompt = "분석해줘"
        tracker = CostTracker(budget_usd=0.002)  # 매우 낮은 예산

        with pytest.raises(BudgetExceededError):
            invoke_llm(
                prompt=prompt,
                items=[],
                tracker=tracker,
                client=mock_client,
            )

        # SDK 호출은 1회 발생, 응답 후 tracker.add() 에서 예외 raise
        assert mock_client.messages.create.call_count == 1

    # AC-I3: System prompt 길이 >= 1000자이면 cache_control 포함
    def test_invoke_cache_control_in_request(self):
        """AC-I3: 긴 system prompt에 cache_control 포함."""
        mock_response = MockMessage()
        mock_client = _make_mock_client(mock_response)

        prompt = "분석"
        long_system_prompt = "x" * 1200

        tracker = CostTracker(budget_usd=10.0)

        invoke_llm(
            prompt=prompt,
            items=[],
            tracker=tracker,
            system_prompt=long_system_prompt,
            client=mock_client,
        )

        assert mock_client.messages.create.called

        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert "system" in call_kwargs
        system_blocks = call_kwargs["system"]
        assert isinstance(system_blocks, list)
        assert len(system_blocks) > 0

        found_cache_control = False
        for block in system_blocks:
            if "cache_control" in block:
                found_cache_control = True
                assert block["cache_control"]["type"] == "ephemeral"

        assert found_cache_control

    # AC-I4: force 인자로 SONNET 강제
    def test_invoke_force_sonnet(self):
        """AC-I4: force=SONNET이면 SONNET SDK 엔드포인트 호출."""
        mock_response = MockMessage(input_tokens=1000, output_tokens=500)
        mock_client = _make_mock_client(mock_response)

        prompt = "분석"  # 짧은 prompt
        tracker = CostTracker(budget_usd=10.0)

        response, new_tracker = invoke_llm(
            prompt=prompt,
            items=[],
            tracker=tracker,
            force=Model.SONNET,
            client=mock_client,
        )

        assert mock_client.messages.create.called

        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert call_kwargs["model"] == "sonnet"

        # SONNET 단가: 1000 input * $3/M + 500 output * $15/M = 0.003 + 0.0075 = 0.0105
        assert new_tracker.usd_spent == pytest.approx(0.0105, abs=1e-6)

    # 긴 텍스트 → SONNET 자동 선택
    def test_invoke_long_text_selects_sonnet(self):
        """긴 텍스트 입력이 SONNET 선택."""
        mock_response = MockMessage()
        mock_client = _make_mock_client(mock_response)

        long_prompt = "x" * 10_000
        tracker = CostTracker(budget_usd=10.0)

        invoke_llm(
            prompt=long_prompt,
            items=[],
            tracker=tracker,
            client=mock_client,
        )

        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert call_kwargs["model"] == "sonnet"

    # 아이템 개수 기반 SONNET 선택
    def test_invoke_many_items_selects_sonnet(self):
        """많은 아이템이 SONNET 선택."""
        mock_response = MockMessage()
        mock_client = _make_mock_client(mock_response)

        prompt = "분석"
        items = list(range(30))
        tracker = CostTracker(budget_usd=10.0)

        invoke_llm(
            prompt=prompt,
            items=items,
            tracker=tracker,
            client=mock_client,
        )

        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert call_kwargs["model"] == "sonnet"

    # usage=None: 경고 로깅 후 tracker 유지
    def test_invoke_no_usage_info(self, caplog):
        """Usage 정보가 없으면 경고 로깅하고 tracker 유지."""
        import logging

        mock_response = MockMessage()
        mock_response.usage = None
        mock_client = _make_mock_client(mock_response)

        prompt = "분석"
        tracker = CostTracker(budget_usd=10.0)

        with caplog.at_level(logging.WARNING, logger="ai.llm.invoke"):
            response, new_tracker = invoke_llm(
                prompt=prompt,
                items=[],
                tracker=tracker,
                client=mock_client,
            )

        # tracker 는 변경 없음 (usage 없으므로)
        assert new_tracker.usd_spent == tracker.usd_spent
        # 경고 로그 확인 (Mi2)
        assert any(
            "usage" in rec.message.lower() and "cost not tracked" in rec.message.lower()
            for rec in caplog.records
        )

    # 빈 system_prompt
    def test_invoke_empty_system_prompt(self):
        """빈 system_prompt도 처리 가능."""
        mock_response = MockMessage()
        mock_client = _make_mock_client(mock_response)

        prompt = "분석"
        tracker = CostTracker(budget_usd=10.0)

        invoke_llm(
            prompt=prompt,
            items=[],
            tracker=tracker,
            system_prompt="",
            client=mock_client,
        )

        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert call_kwargs.get("system") is None or call_kwargs.get("system") == []

    # 누적 비용 추적
    def test_invoke_cumulative_cost_tracking(self):
        """여러 호출의 누적 비용 추적."""
        mock_response = MockMessage(input_tokens=1000, output_tokens=500)
        mock_client = _make_mock_client(mock_response)

        tracker = CostTracker(budget_usd=10.0)

        _, tracker = invoke_llm(
            prompt="A",
            items=[],
            tracker=tracker,
            client=mock_client,
        )
        cost_after_1 = tracker.usd_spent

        _, tracker = invoke_llm(
            prompt="B",
            items=[],
            tracker=tracker,
            client=mock_client,
        )
        cost_after_2 = tracker.usd_spent

        assert cost_after_2 > cost_after_1
        assert cost_after_2 == pytest.approx(cost_after_1 * 2, abs=1e-6)

    # Mi1: kwargs max_tokens 주입 시 충돌 없이 덮어씀
    def test_invoke_max_tokens_kwargs_override(self):
        """Mi1: kwargs로 max_tokens 전달 시 TypeError 없이 덮어쓴다."""
        mock_response = MockMessage()
        mock_client = _make_mock_client(mock_response)

        tracker = CostTracker(budget_usd=10.0)

        invoke_llm(
            prompt="분석",
            items=[],
            tracker=tracker,
            client=mock_client,
            max_tokens=4096,
        )

        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert call_kwargs["max_tokens"] == 4096

    # 기본 max_tokens=2048
    def test_invoke_default_max_tokens(self):
        """max_tokens 미지정 시 기본값 2048."""
        mock_response = MockMessage()
        mock_client = _make_mock_client(mock_response)

        tracker = CostTracker(budget_usd=10.0)

        invoke_llm(
            prompt="분석",
            items=[],
            tracker=tracker,
            client=mock_client,
        )

        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert call_kwargs["max_tokens"] == 2048

    # M5: messages 페이로드 스펙 명시 검증
    def test_invoke_messages_payload_spec(self):
        """M5: messages 가 Anthropic Messages API 스펙 (role/content) 을 따른다."""
        mock_response = MockMessage()
        mock_client = _make_mock_client(mock_response)

        tracker = CostTracker(budget_usd=10.0)
        prompt_text = "테스트 프롬프트"

        invoke_llm(
            prompt=prompt_text,
            items=[],
            tracker=tracker,
            client=mock_client,
        )

        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert call_kwargs["messages"] == [
            {"role": "user", "content": prompt_text}
        ]
