"""reviewer SDK callable wire (F-3) — `_build_reviewer` 동작 검증.

PRD: docs/prd/dev-relay-write-tools.md AC-WT-1 (= F-3 wire 완수)

검증 항목:
- SDK import 실패 시 None 반환 (graceful degradation).
- SDK 가 import 가능하지만 인증이 잘못된 경우 None 반환.
- 정상 환경에서는 callable 반환.
- 응답 raw 텍스트 파싱 동작.
"""

from __future__ import annotations

import importlib
import sys
from unittest import mock

import pytest

from ai.dev_relay import write_runtime
from ai.dev_relay.main import _build_reviewer


class TestBuildReviewerGracefulDegradation:
    def test_no_sdk_returns_none(self, caplog):
        """SDK 모듈 자체가 import 실패해야 하는 환경에서는 None 반환."""
        # write_runtime.is_sdk_available 이 False 면 _build_reviewer 가 None 반환.
        import logging
        logger = logging.getLogger("test_reviewer_wire")
        with mock.patch(
            "ai.dev_relay.write_runtime.is_sdk_available", return_value=False
        ):
            result = _build_reviewer(logger)
            assert result is None

    def test_invalid_api_key_returns_false_from_is_sdk_available(self, monkeypatch):
        """잘못된 API 키 prefix 면 `is_sdk_available()` 가 False."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "invalid-prefix-xxx")
        # claude_agent_sdk import 가능 여부는 환경에 따라 다르므로,
        # SDK 가 import 가능하면 prefix 검증이 작동하는지만 확인.
        try:
            import claude_agent_sdk  # noqa: F401
        except ImportError:
            pytest.skip("claude_agent_sdk not installed in test env")
        assert write_runtime.is_sdk_available() is False

    def test_no_api_key_with_no_sdk_returns_false(self, monkeypatch):
        """SDK 미설치 환경에서 is_sdk_available 가 False 반환."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        # SDK module 자체가 import 안 되도록 mock.
        with mock.patch.dict(sys.modules, {"claude_agent_sdk": None}):
            # is_sdk_available 가 ImportError 를 잡아 False 반환.
            assert write_runtime.is_sdk_available() is False


class TestReviewResponseParsing:
    """SDK 응답 본문 → ReviewResult 파싱 검증."""

    def test_empty_response_returns_fallback(self):
        result = write_runtime._parse_review_response("")
        assert result.summary
        assert result.findings == []

    def test_parses_summary_only(self):
        raw = "PR 가 깔끔합니다. 추가 변경사항 없음."
        result = write_runtime._parse_review_response(raw)
        assert "깔끔" in result.summary
        assert result.findings == []

    def test_parses_findings_section(self):
        raw = (
            "PR 가 양호합니다.\n"
            "발견 사항\n"
            "- 첫 번째 항목\n"
            "- 두 번째 항목\n"
        )
        result = write_runtime._parse_review_response(raw)
        assert "양호" in result.summary
        assert "첫 번째 항목" in result.findings
        assert "두 번째 항목" in result.findings

    def test_detail_preserves_raw(self):
        raw = "본문 일부\n발견 사항\n- 한 줄"
        result = write_runtime._parse_review_response(raw)
        assert result.detail == raw


class TestExtractUnifiedDiff:
    def test_fenced_diff_extracted(self):
        raw = (
            "여기에 패치가 있습니다.\n"
            "```diff\n"
            "--- a/foo.py\n"
            "+++ b/foo.py\n"
            "@@ -1 +1 @@\n"
            "-old\n"
            "+new\n"
            "```\n"
        )
        result = write_runtime._extract_unified_diff(raw)
        assert "--- a/foo.py" in result
        assert "+new" in result

    def test_raw_diff_passthrough(self):
        raw = "--- a/foo.py\n+++ b/foo.py\n@@ -1 +1 @@\n-old\n+new"
        result = write_runtime._extract_unified_diff(raw)
        assert "--- a/foo.py" in result

    def test_empty_returns_empty(self):
        assert write_runtime._extract_unified_diff("") == ""
