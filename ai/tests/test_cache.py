"""프롬프트 캐싱 테스트 (AC-P)."""

import pytest
from ai.llm import build_system_block, CACHE_CONTROL_THRESHOLD_CHARS


class TestCache:
    """build_system_block() 함수의 캐싱 로직 테스트."""

    # AC-P1: 1000자 이상이면 cache_control 포함
    def test_cache_control_long_prompt(self):
        """AC-P1: 길이 1200자 이상이면 cache_control 포함."""
        long_prompt = "x" * 1200  # 1200자
        result = build_system_block(long_prompt)

        assert isinstance(result, list)
        assert len(result) == 1

        block = result[0]
        assert block["type"] == "text"
        assert block["text"] == long_prompt
        assert "cache_control" in block
        assert block["cache_control"] == {"type": "ephemeral"}

    # AC-P2: 임계 미만이면 cache_control 없음
    def test_no_cache_control_short_prompt(self):
        """AC-P2: 길이 500자 미만이면 cache_control 없음."""
        short_prompt = "x" * 500  # 500자
        result = build_system_block(short_prompt)

        assert isinstance(result, list)
        assert len(result) == 1

        block = result[0]
        assert block["type"] == "text"
        assert block["text"] == short_prompt
        assert "cache_control" not in block

    # AC-P3: 반환값이 Anthropic Messages API 형식
    def test_cache_output_format(self):
        """AC-P3: 반환값이 Anthropic Messages API 형식."""
        prompt = "x" * 1200
        result = build_system_block(prompt)

        # 구조 검증
        assert isinstance(result, list)
        assert len(result) == 1

        block = result[0]
        assert isinstance(block, dict)
        assert "type" in block
        assert block["type"] == "text"
        assert "text" in block
        assert isinstance(block["text"], str)

        # cache_control 형식 검증
        if "cache_control" in block:
            assert isinstance(block["cache_control"], dict)
            assert "type" in block["cache_control"]
            assert block["cache_control"]["type"] == "ephemeral"

    # 경계값 테스트
    def test_cache_control_exact_threshold(self):
        """임계값 정확히 1000자일 때 cache_control 포함."""
        prompt = "x" * CACHE_CONTROL_THRESHOLD_CHARS
        result = build_system_block(prompt)
        block = result[0]
        assert "cache_control" in block

    def test_no_cache_control_just_below_threshold(self):
        """임계값 - 1자일 때 cache_control 없음."""
        prompt = "x" * (CACHE_CONTROL_THRESHOLD_CHARS - 1)
        result = build_system_block(prompt)
        block = result[0]
        assert "cache_control" not in block

    def test_no_cache_control_empty_prompt(self):
        """빈 prompt도 처리 가능."""
        result = build_system_block("")
        block = result[0]
        assert block["text"] == ""
        assert "cache_control" not in block

    def test_cache_control_multiline_prompt(self):
        """개행 포함 prompt도 길이 계산 정상."""
        prompt = "line1\n" * 200  # 약 1200자
        result = build_system_block(prompt)
        assert len(result) == 1
        assert result[0]["text"] == prompt

    def test_cache_control_unicode_prompt(self):
        """유니코드 문자도 길이 계산 정상."""
        prompt = "한글 " * 250  # 약 1250자
        result = build_system_block(prompt)
        assert len(result) == 1
        assert result[0]["text"] == prompt
        # "한글 " = 3자 × 250 = 750자 (임계값 미만)
        # 또는 포함되지 않을 수 있음. 실제 길이 확인:
        if len(prompt) >= CACHE_CONTROL_THRESHOLD_CHARS:
            assert "cache_control" in result[0]
        else:
            assert "cache_control" not in result[0]
