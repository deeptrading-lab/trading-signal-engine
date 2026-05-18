"""write 도구 (apply patch / commit / push) 단위 테스트.

PRD: docs/prd/dev-relay-write-tools.md AC-WT-2 ~ AC-WT-6

본 파일은 다음 케이스를 mock 으로 검증한다.
- patch destructive 가드 (AC-WT-5)
- patch 적용 dry-run / 실 호출
- commit 메시지 가드 (AC-WT-15)
- push 정책 가드
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass

import pytest

from ai.dev_relay.write_tools import (
    CommitMessageBlocked,
    PatchDestructiveBlocked,
    PushPolicyBlocked,
    WriteToolError,
    apply_patch,
    check_commit_message,
    check_patch_destructive,
    check_push_policy,
    perform_commit,
    perform_push,
    preview_commit,
    preview_patch,
    preview_push,
)


# ---------------------------------------------------------------------------
# fake subprocess runner
# ---------------------------------------------------------------------------


@dataclass
class FakeCompleted:
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""


def make_runner(*, by_args: dict[tuple[str, ...], FakeCompleted] | None = None,
                default: FakeCompleted | None = None):
    """args tuple → FakeCompleted 매핑 기반 runner.

    매칭 키는 args 의 prefix 이며, 가장 긴 매치를 우선한다.
    """
    by_args = by_args or {}
    default = default or FakeCompleted(returncode=0)
    calls: list[tuple[tuple[str, ...], dict]] = []

    def _runner(args, **kwargs):
        args_t = tuple(args)
        calls.append((args_t, kwargs))
        # 가장 긴 prefix 매치.
        best: FakeCompleted | None = None
        best_len = -1
        for key, completed in by_args.items():
            if args_t[: len(key)] == key and len(key) > best_len:
                best = completed
                best_len = len(key)
        return best if best is not None else default

    return _runner, calls


# ---------------------------------------------------------------------------
# AC-WT-5: destructive 가드
# ---------------------------------------------------------------------------


SAMPLE_PATCH = (
    "--- a/ai/dev_relay/foo.py\n"
    "+++ b/ai/dev_relay/foo.py\n"
    "@@ -1,3 +1,3 @@\n"
    "-old line\n"
    "+new line\n"
    " context line\n"
)


class TestPatchDestructiveGuard:
    def test_clean_patch_passes(self):
        check_patch_destructive(SAMPLE_PATCH)

    @pytest.mark.parametrize(
        "patch_body",
        [
            "+rm -rf /\n",
            "+echo > /dev/null\n",
            "+git push --force\n",
            "+git reset --hard HEAD~5\n",
            "+ filter-branch goes here\n",
        ],
    )
    def test_destructive_body_blocked(self, patch_body: str):
        full = (
            "--- a/foo.py\n+++ b/foo.py\n@@ -1 +1 @@\n" + patch_body
        )
        with pytest.raises(PatchDestructiveBlocked):
            check_patch_destructive(full)

    @pytest.mark.parametrize(
        "target_path",
        [
            ".env",
            ".env.local",
            ".env.production",
            ".git/config",
            "secrets/db.yml",
            "service.key",
            "cert.pem",
            "credentials.json",
        ],
    )
    def test_forbidden_path_blocked(self, target_path: str):
        full = (
            f"--- a/{target_path}\n+++ b/{target_path}\n@@ -1 +1 @@\n-x\n+y\n"
        )
        with pytest.raises(PatchDestructiveBlocked):
            check_patch_destructive(full)

    def test_empty_patch_blocked(self):
        with pytest.raises(PatchDestructiveBlocked):
            check_patch_destructive("")


# ---------------------------------------------------------------------------
# AC-WT-2: patch preview + apply
# ---------------------------------------------------------------------------


class TestPatchPreview:
    def test_preview_extracts_files_and_lines(self):
        preview = preview_patch(SAMPLE_PATCH)
        assert preview.files == ("ai/dev_relay/foo.py",)
        assert preview.lines_added == 1
        assert preview.lines_removed == 1

    def test_preview_destructive_raises(self):
        bad = (
            "--- a/.env\n+++ b/.env\n@@ -1 +1 @@\n-x\n+y\n"
        )
        with pytest.raises(PatchDestructiveBlocked):
            preview_patch(bad)


class TestApplyPatch:
    def test_apply_calls_git_check_then_apply(self):
        runner, calls = make_runner()
        applied = apply_patch(SAMPLE_PATCH, runner=runner)
        assert applied == ("ai/dev_relay/foo.py",)
        # 2 호출 — check + 실 적용.
        assert calls[0][0][:3] == ("git", "apply", "--check")
        assert calls[1][0][:2] == ("git", "apply")

    def test_apply_check_failure_raises(self):
        runner, _ = make_runner(
            by_args={
                ("git", "apply", "--check"): FakeCompleted(returncode=1, stderr="bad"),
            }
        )
        with pytest.raises(WriteToolError):
            apply_patch(SAMPLE_PATCH, runner=runner)

    def test_apply_destructive_blocks_before_subprocess(self):
        runner, calls = make_runner()
        bad = "--- a/.env\n+++ b/.env\n@@ -1 +1 @@\n-x\n+y\n"
        with pytest.raises(PatchDestructiveBlocked):
            apply_patch(bad, runner=runner)
        # subprocess 호출 0 — 가드 1차 차단.
        assert len(calls) == 0


# ---------------------------------------------------------------------------
# AC-WT-3 / AC-WT-15: commit 메시지 가드 + preview + perform
# ---------------------------------------------------------------------------


class TestCommitMessageGuard:
    def test_clean_message_passes(self):
        check_commit_message("리뷰 피드백 반영")

    def test_empty_message_blocked(self):
        with pytest.raises(CommitMessageBlocked):
            check_commit_message("")
        with pytest.raises(CommitMessageBlocked):
            check_commit_message("   ")

    def test_domain_keyword_blocked(self):
        # 컴플라이언스 가드 — 도메인 키워드 포함.
        with pytest.raises(CommitMessageBlocked):
            check_commit_message("signal 처리 개선")

    @pytest.mark.parametrize(
        "msg",
        [
            "--amend HEAD",
            "fix --no-verify",
        ],
    )
    def test_forbidden_flag_blocked(self, msg: str):
        with pytest.raises(CommitMessageBlocked):
            check_commit_message(msg)


class TestCommitPreview:
    def test_preview_with_staged_changes(self):
        runner, _ = make_runner(
            by_args={
                ("git", "diff", "--cached", "--name-only"): FakeCompleted(
                    returncode=0, stdout="ai/foo.py\nai/bar.py\n"
                ),
            }
        )
        preview = preview_commit("개선 반영", runner=runner, auto_stage=False)
        assert preview.message == "개선 반영"
        assert "ai/foo.py" in preview.staged_files
        assert "ai/bar.py" in preview.staged_files

    def test_preview_empty_tree_blocked(self):
        runner, _ = make_runner(
            by_args={
                ("git", "diff", "--cached", "--name-only"): FakeCompleted(
                    returncode=0, stdout=""
                ),
            }
        )
        with pytest.raises(WriteToolError) as exc_info:
            preview_commit("개선 반영", runner=runner, auto_stage=False)
        assert "commit_empty_tree" in str(exc_info.value)


class TestPerformCommit:
    def test_commit_returns_short_sha(self):
        runner, _ = make_runner(
            by_args={
                ("git", "commit"): FakeCompleted(returncode=0),
                ("git", "rev-parse", "HEAD"): FakeCompleted(
                    returncode=0, stdout="abcdef1234567890\n"
                ),
            }
        )
        sha = perform_commit("개선 반영", runner=runner)
        assert sha == "abcdef123456"

    def test_commit_empty_tree_classification(self):
        runner, _ = make_runner(
            by_args={
                ("git", "commit"): FakeCompleted(
                    returncode=1, stderr="nothing to commit, working tree clean"
                ),
            }
        )
        with pytest.raises(WriteToolError) as exc_info:
            perform_commit("개선 반영", runner=runner)
        assert "commit_empty_tree" in str(exc_info.value)


# ---------------------------------------------------------------------------
# AC-WT-4 / AC-WT-5: push 정책 가드
# ---------------------------------------------------------------------------


class TestPushPolicyGuard:
    def test_clean_branch_passes(self):
        check_push_policy("feature/foo")

    @pytest.mark.parametrize(
        "branch",
        ["main", "master", "develop", "release"],
    )
    def test_protected_branch_blocked(self, branch: str):
        with pytest.raises(PushPolicyBlocked):
            check_push_policy(branch)

    def test_empty_branch_blocked(self):
        with pytest.raises(PushPolicyBlocked):
            check_push_policy("")

    def test_forbidden_opt_blocked(self):
        with pytest.raises(PushPolicyBlocked):
            check_push_policy("feature/foo", extra_opts=["--force"])


class TestPushPreview:
    def test_preview_returns_branch_and_remote(self):
        runner, _ = make_runner(
            by_args={
                ("git", "branch", "--show-current"): FakeCompleted(
                    returncode=0, stdout="feature/foo\n"
                ),
                ("git", "log", "--pretty=%h"): FakeCompleted(
                    returncode=0, stdout="abc123\ndef456\n"
                ),
            }
        )
        preview = preview_push(runner=runner)
        assert preview.branch == "feature/foo"
        assert preview.remote == "origin"
        assert "abc123" in preview.commit_shas

    def test_preview_protected_branch_blocked(self):
        runner, _ = make_runner(
            by_args={
                ("git", "branch", "--show-current"): FakeCompleted(
                    returncode=0, stdout="main\n"
                ),
            }
        )
        with pytest.raises(PushPolicyBlocked):
            preview_push(runner=runner)


class TestPerformPush:
    def test_push_calls_git_push(self):
        runner, calls = make_runner(
            by_args={
                ("git", "branch", "--show-current"): FakeCompleted(
                    returncode=0, stdout="feature/foo\n"
                ),
                ("git", "push"): FakeCompleted(returncode=0),
            }
        )
        remote, branch = perform_push(runner=runner)
        assert remote == "origin"
        assert branch == "feature/foo"
        # git push 호출 검증.
        push_calls = [c for c in calls if c[0][:2] == ("git", "push")]
        assert len(push_calls) == 1
        assert push_calls[0][0] == ("git", "push", "origin", "feature/foo")

    def test_push_rejected_classification(self):
        runner, _ = make_runner(
            by_args={
                ("git", "branch", "--show-current"): FakeCompleted(
                    returncode=0, stdout="feature/foo\n"
                ),
                ("git", "push"): FakeCompleted(
                    returncode=1, stderr="error: failed to push some refs (non-fast-forward)"
                ),
            }
        )
        with pytest.raises(WriteToolError) as exc_info:
            perform_push(runner=runner)
        assert "push_rejected" in str(exc_info.value)
