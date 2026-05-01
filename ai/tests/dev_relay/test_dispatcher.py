"""dispatcher 명령 파싱 단위 테스트 (PRD §3.3 / AC-13)."""

from __future__ import annotations

import pytest

from ai.dev_relay.dispatcher import (
    CommandKind,
    is_destructive,
    normalize,
    parse,
)


class TestNormalize:
    def test_empty_returns_empty(self):
        assert normalize(None) == ""
        assert normalize("") == ""

    def test_trims_and_lowers(self):
        assert normalize("  STATUS  ") == "status"

    def test_collapses_whitespace(self):
        assert normalize("review   pr   22") == "review pr 22"

    def test_tabs_collapsed_to_single_space(self):
        assert normalize("review\tpr\t22") == "review pr 22"


class TestParseStatus:
    def test_status_lowercase(self):
        cmd = parse("status")
        assert cmd.kind is CommandKind.STATUS
        assert cmd.normalized == "status"
        assert cmd.pr_number is None

    def test_status_uppercase_and_padding(self):
        cmd = parse("  STATUS  ")
        assert cmd.kind is CommandKind.STATUS


class TestParseReviewPr:
    def test_basic(self):
        cmd = parse("review pr 22")
        assert cmd.kind is CommandKind.REVIEW_PR
        assert cmd.pr_number == 22
        assert cmd.normalized == "review pr 22"

    def test_extra_whitespace(self):
        cmd = parse("review   pr   22")
        assert cmd.kind is CommandKind.REVIEW_PR
        assert cmd.pr_number == 22

    def test_uppercase(self):
        cmd = parse("REVIEW PR 22")
        assert cmd.kind is CommandKind.REVIEW_PR
        assert cmd.pr_number == 22

    def test_non_integer_falls_through(self):
        cmd = parse("review pr abc")
        assert cmd.kind is CommandKind.UNKNOWN

    def test_extra_tail_falls_through(self):
        # 여분 토큰은 unknown 처리.
        cmd = parse("review pr 22 please")
        assert cmd.kind is CommandKind.UNKNOWN


class TestParseMergePr:
    def test_basic(self):
        cmd = parse("merge pr 5")
        assert cmd.kind is CommandKind.MERGE_PR
        assert cmd.pr_number == 5
        assert cmd.normalized == "merge pr 5"

    def test_uppercase(self):
        cmd = parse("MERGE PR 5")
        assert cmd.kind is CommandKind.MERGE_PR

    def test_non_integer_falls_through(self):
        cmd = parse("merge pr xyz")
        assert cmd.kind is CommandKind.UNKNOWN


class TestParseUnknown:
    def test_empty_is_unknown(self):
        cmd = parse("")
        assert cmd.kind is CommandKind.UNKNOWN

    def test_random_text_is_unknown(self):
        cmd = parse("hello there")
        assert cmd.kind is CommandKind.UNKNOWN

    def test_partial_review_is_unknown(self):
        # `review pr` 만으로는 매치되지 않는다.
        cmd = parse("review pr")
        assert cmd.kind is CommandKind.UNKNOWN


class TestDestructiveDetection:
    @pytest.mark.parametrize(
        "text",
        [
            "git reset --hard HEAD~5",
            "force push main",
            "git push --force",
            "git push -f",
            "git branch -D feature/foo",
            "git clean -f",
            "git clean -fd",
            "rebase --hard",
            "git checkout -- file.txt",
            "git restore -- file.txt",
        ],
    )
    def test_destructive_strings_detected(self, text: str):
        assert is_destructive(text) is True

    @pytest.mark.parametrize(
        "text",
        [
            "status",
            "review pr 22",
            "merge pr 5",
            "git status",
            "git log",
            "git diff",
        ],
    )
    def test_clean_strings_pass(self, text: str):
        assert is_destructive(text) is False

    def test_destructive_routes_to_blocked(self):
        cmd = parse("git reset --hard HEAD~5")
        assert cmd.kind is CommandKind.DESTRUCTIVE_BLOCKED

    def test_destructive_takes_precedence_over_known_command(self):
        # `merge pr 5; git push --force` 류는 unknown 으로 떨어지더라도
        # destructive 표지가 우선 차단한다.
        cmd = parse("merge pr 5 then git push --force")
        assert cmd.kind is CommandKind.DESTRUCTIVE_BLOCKED
