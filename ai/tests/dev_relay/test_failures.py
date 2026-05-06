"""실패 분류 매핑 단위 테스트 (PRD `dev-relay-agent-integration.md` AC-INT-5)."""

from __future__ import annotations

import pytest

from ai.dev_relay.agent_runner import DestructiveOperationBlocked
from ai.dev_relay.failures import (
    FailureClassification,
    classify_exception,
    classify_github_status,
    report,
    user_message_for,
)
from ai.dev_relay.slack_renderer import (
    TEMPLATE_FAIL_COMPLIANCE_BLOCKED,
    TEMPLATE_FAIL_DESTRUCTIVE_BLOCKED,
    TEMPLATE_FAIL_GITHUB_UNAUTHORIZED,
    TEMPLATE_FAIL_GITHUB_UNPROCESSABLE,
    TEMPLATE_FAIL_SDK_TIMEOUT,
    TEMPLATE_FAIL_UNKNOWN,
)


class TestUserMessageMapping:
    """5개 분류 + fallback 모두 정적 템플릿과 정확히 매핑되는지."""

    @pytest.mark.parametrize(
        "classification,expected_template",
        [
            (FailureClassification.DESTRUCTIVE_BLOCKED, TEMPLATE_FAIL_DESTRUCTIVE_BLOCKED),
            (FailureClassification.SDK_TIMEOUT, TEMPLATE_FAIL_SDK_TIMEOUT),
            (FailureClassification.GITHUB_UNAUTHORIZED, TEMPLATE_FAIL_GITHUB_UNAUTHORIZED),
            (FailureClassification.GITHUB_UNPROCESSABLE, TEMPLATE_FAIL_GITHUB_UNPROCESSABLE),
            (FailureClassification.COMPLIANCE_BLOCKED, TEMPLATE_FAIL_COMPLIANCE_BLOCKED),
            (FailureClassification.UNKNOWN_ERROR, TEMPLATE_FAIL_UNKNOWN),
        ],
    )
    def test_each_classification_maps_to_template(
        self, classification: FailureClassification, expected_template: str
    ):
        assert user_message_for(classification) == expected_template


class TestClassifyGithubStatus:
    @pytest.mark.parametrize("code", [401, 403])
    def test_auth_codes(self, code: int):
        assert classify_github_status(code) is FailureClassification.GITHUB_UNAUTHORIZED

    def test_unprocessable(self):
        assert classify_github_status(422) is FailureClassification.GITHUB_UNPROCESSABLE

    @pytest.mark.parametrize("code", [200, 500, 502, 999])
    def test_other_codes_fallback(self, code: int):
        assert classify_github_status(code) is FailureClassification.UNKNOWN_ERROR


class TestClassifyException:
    def test_destructive_blocked(self):
        exc = DestructiveOperationBlocked("blocked")
        assert classify_exception(exc) is FailureClassification.DESTRUCTIVE_BLOCKED

    def test_timeout(self):
        exc = TimeoutError("waited too long")
        assert classify_exception(exc) is FailureClassification.SDK_TIMEOUT

    def test_unknown_fallback(self):
        exc = ValueError("nope")
        assert classify_exception(exc) is FailureClassification.UNKNOWN_ERROR

    def test_custom_timeout_marker(self):
        class MyTimeout(Exception):
            pass

        exc = MyTimeout("dom timeout")
        assert (
            classify_exception(exc, timeout_marker_types=(MyTimeout,))
            is FailureClassification.SDK_TIMEOUT
        )


class TestReport:
    def test_report_packages_classification_and_message(self):
        rep = report(FailureClassification.GITHUB_UNAUTHORIZED, detail="gh stderr 401")
        assert rep.classification is FailureClassification.GITHUB_UNAUTHORIZED
        assert rep.user_message == TEMPLATE_FAIL_GITHUB_UNAUTHORIZED
        assert "401" in rep.detail
