"""코디네이터 명령 라우팅·응답 텍스트 테스트 (AC-2, AC-3, AC-4, AC-8)."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from ai.coordinator.handlers import (
    KST,
    normalize_command,
    render_fallback,
    render_ping,
    render_status,
    route_command,
)


# AC-8: 외부 노출 텍스트에 등장 금지 키워드.
FORBIDDEN_KEYWORDS = (
    "signal",
    "trade",
    "trading",
    "desk",
    "quant",
    "finance",
    "market",
    "ticker",
    "pnl",
)


def assert_no_forbidden_keywords(text: str) -> None:
    """AC-8 컴플라이언스 헬퍼."""
    lower = text.lower()
    for keyword in FORBIDDEN_KEYWORDS:
        assert keyword not in lower, (
            f"외부 노출 응답에 금지 키워드 '{keyword}' 가 포함됨: {text!r}"
        )


class TestNormalizeCommand:
    """AC-4: 트림·대소문자 정규화."""

    def test_trim_and_lower(self):
        assert normalize_command("  PING  ") == "ping"

    def test_already_normalized(self):
        assert normalize_command("status") == "status"

    def test_none(self):
        assert normalize_command(None) == ""

    def test_empty(self):
        assert normalize_command("") == ""

    def test_whitespace_only(self):
        assert normalize_command("   ") == ""


class TestRenderPing:
    """AC-2: `ping` → `pong`."""

    def test_pong(self):
        assert render_ping() == "pong"

    def test_no_forbidden_keywords(self):
        assert_no_forbidden_keywords(render_ping())


class TestRenderStatus:
    """AC-3: 상태 응답 4종 정보 포함."""

    def test_includes_uptime_hostname_time_python(self):
        text = render_status(
            now_provider=lambda: datetime(2026, 5, 1, 12, 30, 45, tzinfo=KST),
            monotonic_provider=lambda: 100.0,
            hostname_provider=lambda: "test-host",
            python_version_provider=lambda: "3.11.7",
            process_start_monotonic=0.0,
        )
        assert "0d 00:01:40" in text  # 100s = 1분 40초
        assert "test-host" in text
        assert "2026-05-01T12:30:45+09:00" in text
        assert "3.11.7" in text

    def test_uptime_format_days_hours_minutes_seconds(self):
        text = render_status(
            now_provider=lambda: datetime(2026, 5, 1, 0, 0, 0, tzinfo=KST),
            monotonic_provider=lambda: 86_400 + 3_600 + 60 + 5,  # 1d 01:01:05
            hostname_provider=lambda: "h",
            python_version_provider=lambda: "3.11.0",
            process_start_monotonic=0.0,
        )
        assert "1d 01:01:05" in text

    def test_uses_kst_timezone(self):
        # UTC 12:00 → KST 21:00.
        utc_noon = datetime(2026, 5, 1, 12, 0, 0, tzinfo=timezone.utc)
        text = render_status(
            now_provider=lambda: utc_noon,
            monotonic_provider=lambda: 0.0,
            hostname_provider=lambda: "h",
            python_version_provider=lambda: "3.11.0",
            process_start_monotonic=0.0,
        )
        assert "2026-05-01T21:00:00+09:00" in text

    def test_self_reference_uses_neutral_term(self):
        text = render_status(
            now_provider=lambda: datetime(2026, 5, 1, 12, 0, 0, tzinfo=KST),
            monotonic_provider=lambda: 0.0,
            hostname_provider=lambda: "h",
            python_version_provider=lambda: "3.11.0",
            process_start_monotonic=0.0,
        )
        assert "코디네이터" in text

    def test_no_forbidden_keywords(self):
        text = render_status(
            now_provider=lambda: datetime(2026, 5, 1, 12, 0, 0, tzinfo=KST),
            monotonic_provider=lambda: 12345.6,
            hostname_provider=lambda: "host-1",
            python_version_provider=lambda: "3.11.7",
            process_start_monotonic=0.0,
        )
        assert_no_forbidden_keywords(text)

    def test_iso_8601_format(self):
        text = render_status(
            now_provider=lambda: datetime(2026, 5, 1, 9, 8, 7, tzinfo=KST),
            monotonic_provider=lambda: 0.0,
            hostname_provider=lambda: "h",
            python_version_provider=lambda: "3.11.0",
            process_start_monotonic=0.0,
        )
        # ISO-8601 with offset.
        assert re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+09:00", text)


class TestRenderFallback:
    """AC-4: 알 수 없는 명령 안내."""

    def test_lists_known_commands(self):
        text = render_fallback()
        assert "ping" in text
        assert "status" in text

    def test_no_forbidden_keywords(self):
        assert_no_forbidden_keywords(render_fallback())


class TestRouteCommand:
    """AC-2/AC-3/AC-4 종합 라우팅."""

    def test_ping_routes_to_pong(self):
        assert route_command("ping") == "pong"

    def test_ping_with_whitespace_and_caps(self):
        assert route_command("  PING  ") == "pong"
        assert route_command("Ping") == "pong"

    def test_status_routes_to_status_render(self):
        text = route_command("status")
        assert "코디네이터" in text
        assert "Python" in text

    def test_unknown_falls_back(self):
        text = route_command("asdf")
        assert "ping" in text
        assert "status" in text

    def test_help_falls_back(self):
        text = route_command("help")
        assert "ping" in text and "status" in text

    def test_empty_falls_back(self):
        text = route_command("")
        assert "ping" in text and "status" in text

    def test_none_falls_back(self):
        text = route_command(None)
        assert "ping" in text and "status" in text

    def test_all_routed_outputs_have_no_forbidden_keywords(self):
        for inp in ["ping", "status", "asdf", "help", "  PING  ", "", None]:
            assert_no_forbidden_keywords(route_command(inp))
