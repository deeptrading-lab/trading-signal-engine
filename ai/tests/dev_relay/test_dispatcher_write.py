"""dispatcher write 도구 명령 파싱 단위 테스트.

PRD: docs/prd/dev-relay-write-tools.md §3.2.3 / AC-WT-2 ~ AC-WT-5
"""

from __future__ import annotations

import pytest

from ai.dev_relay.dispatcher import CommandKind, parse


class TestParseApplyPatch:
    def test_basic(self):
        cmd = parse("apply patch pr=22")
        assert cmd.kind is CommandKind.APPLY_PATCH_PR
        assert cmd.pr_number == 22
        assert cmd.normalized == "apply patch pr=22"

    def test_uppercase(self):
        cmd = parse("APPLY PATCH PR=22")
        assert cmd.kind is CommandKind.APPLY_PATCH_PR
        assert cmd.pr_number == 22

    def test_whitespace_around_equals(self):
        cmd = parse("apply patch pr = 22")
        assert cmd.kind is CommandKind.APPLY_PATCH_PR
        assert cmd.pr_number == 22


class TestParseCommit:
    def test_basic(self):
        cmd = parse("commit pr=22")
        assert cmd.kind is CommandKind.COMMIT_PR
        assert cmd.pr_number == 22

    def test_uppercase(self):
        cmd = parse("COMMIT PR=22")
        assert cmd.kind is CommandKind.COMMIT_PR


class TestParsePush:
    def test_basic(self):
        cmd = parse("push pr=22")
        assert cmd.kind is CommandKind.PUSH_PR
        assert cmd.pr_number == 22

    def test_uppercase(self):
        cmd = parse("PUSH PR=22")
        assert cmd.kind is CommandKind.PUSH_PR


class TestWriteCommandDestructiveStillBlocked:
    """write 도구 명령에 destructive 표지가 섞이면 destructive 라우팅 유지."""

    @pytest.mark.parametrize(
        "text",
        [
            "apply patch pr=22 && push --force",
            "commit pr=22 --amend",
            "push pr=22 --force",
            "push pr=22 with force-with-lease",
        ],
    )
    def test_destructive_takes_precedence(self, text: str):
        cmd = parse(text)
        assert cmd.kind is CommandKind.DESTRUCTIVE_BLOCKED


class TestWriteCommandsArePrNumberRequired:
    """write 도구는 `pr=<N>` 인자 강제 — 누락 시 unknown."""

    @pytest.mark.parametrize(
        "text",
        [
            "apply patch",
            "apply patch pr=",
            "commit",
            "commit pr=abc",
            "push",
        ],
    )
    def test_missing_or_invalid_pr(self, text: str):
        cmd = parse(text)
        assert cmd.kind in (CommandKind.UNKNOWN, CommandKind.DESTRUCTIVE_BLOCKED)
