"""SDK PreToolUse 정책 단위 테스트 (PRD AC-9 ~ AC-14, AC-16).

검증 항목:
- AC-9: Read 허용 (일반 파일).
- AC-10: Edit/Write 일체 거부.
- AC-11: Bash mutating 명령 거부.
- AC-12: Bash read-only 명령 허용.
- AC-13: 비밀 파일 패턴 Read 거부.
- AC-14: WebFetch 도메인 화이트리스트.
- AC-16: SDK 응답 destructive 표지가 도구 입력으로 흘러도 거부.
"""

from __future__ import annotations

import pytest

from ai.dev_relay.tool_policy import ALLOWED_TOOLS, DENIED_TOOLS, evaluate


# ---------------------------------------------------------------------------
# AC-9: Read 허용
# ---------------------------------------------------------------------------


class TestReadAllowed:
    def test_read_handoff(self):
        decision = evaluate("Read", {"file_path": "docs/HANDOFF.md"})
        assert decision.allowed is True
        assert decision.reason is None

    def test_read_python_source(self):
        decision = evaluate(
            "Read", {"file_path": "ai/dev_relay/dispatcher.py"}
        )
        assert decision.allowed is True

    def test_read_absolute_path(self):
        decision = evaluate(
            "Read", {"file_path": "/Users/foo/code/repo/README.md"}
        )
        assert decision.allowed is True


# ---------------------------------------------------------------------------
# AC-13: 비밀 파일 패턴 Read 거부
# ---------------------------------------------------------------------------


class TestReadSecretBlocked:
    @pytest.mark.parametrize(
        "path",
        [
            ".env",
            ".env.local",
            ".env.production",
            "ai/.env",
            "secrets/api-key.json",
            "config/secrets/db.yaml",
            "github-token.txt",
            "my_credential.pem",
            "credentials.json",
        ],
    )
    def test_secret_paths_denied(self, path: str):
        decision = evaluate("Read", {"file_path": path})
        assert decision.allowed is False
        assert decision.reason == "secret_pattern"


# ---------------------------------------------------------------------------
# AC-10: Edit/Write 일체 거부
# ---------------------------------------------------------------------------


class TestWriteToolsDenied:
    @pytest.mark.parametrize("name", ["Edit", "Write", "NotebookEdit"])
    def test_write_tool_denied(self, name: str):
        decision = evaluate(name, {"file_path": "ai/dev_relay/main.py"})
        assert decision.allowed is False
        assert decision.reason == "phase1_readonly"

    def test_unknown_tool_denied(self):
        decision = evaluate("MysteryTool", {"foo": "bar"})
        assert decision.allowed is False
        assert decision.reason == "not_whitelisted"


# ---------------------------------------------------------------------------
# AC-12: Bash read-only 화이트리스트 허용
# ---------------------------------------------------------------------------


class TestBashReadOnlyAllowed:
    @pytest.mark.parametrize(
        "cmd",
        [
            "git log -n 20",
            "git status",
            "git diff HEAD~1",
            "git show HEAD",
            "git branch --show-current",
            "git rev-parse HEAD",
            "gh pr list --state open",
            "gh pr view 25",
            "gh issue list",
            "gh issue view 31",
            "gh repo view",
            "cat README.md",
            "head -n 50 docs/HANDOFF.md",
            "tail -n 20 ai/main.py",
            "wc -l ai/main.py",
            "ls -la docs/prd",
            "pwd",
            "find docs -name '*.md'",
            "pytest --collect-only ai/tests",
        ],
    )
    def test_readonly_commands_allowed(self, cmd: str):
        decision = evaluate("Bash", {"command": cmd})
        assert decision.allowed is True, f"expected allow: {cmd} ({decision.reason})"


# ---------------------------------------------------------------------------
# AC-11: Bash mutating 명령 거부
# ---------------------------------------------------------------------------


class TestBashMutatingDenied:
    @pytest.mark.parametrize(
        "cmd",
        [
            "git commit -m 'test'",
            "git push origin main",
            "git merge main",
            "git rebase main",
            "git reset --hard HEAD~1",
            "git checkout main",
            "git stash",
            "git clean -f",
            "git branch -D feature/old",
            "gh pr create --title test",
            "gh pr merge 25",
            "gh issue create --title bug",
            "rm -rf docs",
            "mv a b",
            "cp a b",
            "mkdir new-dir",
            "touch new-file",
            "chmod 755 file",
            "npm install lodash",
            "pip install foo",
            "python -c 'print(1)'",
            "python3 script.py",
            "bash run.sh",
            "echo hello > out.txt",
            "ls > out.txt",
            "cat a | tee b",
            "true && false",
            "ls; rm a",
            "find docs -name '*.md' -delete",
            "find . -exec rm {} \\;",
            "pytest ai/tests",  # 실제 테스트 실행은 거부 (collect-only 만 허용)
        ],
    )
    def test_mutating_commands_denied(self, cmd: str):
        decision = evaluate("Bash", {"command": cmd})
        assert decision.allowed is False, f"expected deny: {cmd}"


# ---------------------------------------------------------------------------
# AC-16: SDK 응답에 destructive 표지가 섞인 경우
# ---------------------------------------------------------------------------


class TestBashDestructiveDenied:
    @pytest.mark.parametrize(
        "cmd",
        [
            "git reset --hard HEAD~5",
            "git push --force",
            "git push -f origin main",
            "git checkout -- .",
            "git restore -- src/",
            "git clean -fd",
        ],
    )
    def test_destructive_patterns_denied(self, cmd: str):
        decision = evaluate("Bash", {"command": cmd})
        assert decision.allowed is False
        assert decision.reason in {"destructive_command", "mutating_command"}


# ---------------------------------------------------------------------------
# AC-14: WebFetch 도메인 화이트리스트
# ---------------------------------------------------------------------------


class TestWebFetchDomain:
    @pytest.mark.parametrize(
        "url",
        [
            "https://github.com/example/repo/pull/25",
            "https://api.github.com/repos/example/repo/issues",
            "https://docs.anthropic.com/en/api/messages",
            "https://docs.python.org/3/library/re.html",
        ],
    )
    def test_allowed_hosts(self, url: str):
        decision = evaluate("WebFetch", {"url": url})
        assert decision.allowed is True

    @pytest.mark.parametrize(
        "url",
        [
            "https://internal-wiki.example.com/secret",
            "http://malicious.example/payload",
            "https://stackoverflow.com/q/123",
            "https://gist.github.com/foo",  # 서브도메인 매치 비활성 (보수)
            "https://raw.githubusercontent.com/foo",
            "ftp://github.com/foo",  # scheme 거부
            "file:///etc/passwd",
            "",
        ],
    )
    def test_denied_hosts(self, url: str):
        decision = evaluate("WebFetch", {"url": url})
        assert decision.allowed is False
        if url:
            assert decision.reason == "domain_not_allowed"


# ---------------------------------------------------------------------------
# Glob / Grep 허용
# ---------------------------------------------------------------------------


class TestGlobGrepAllowed:
    def test_glob(self):
        decision = evaluate("Glob", {"pattern": "**/*.py"})
        assert decision.allowed is True

    def test_grep(self):
        decision = evaluate("Grep", {"pattern": "TODO"})
        assert decision.allowed is True


# ---------------------------------------------------------------------------
# 모듈 export 일관성
# ---------------------------------------------------------------------------


def test_allowed_and_denied_disjoint():
    assert ALLOWED_TOOLS.isdisjoint(DENIED_TOOLS)


def test_phase1_no_write_in_allowed():
    assert "Edit" not in ALLOWED_TOOLS
    assert "Write" not in ALLOWED_TOOLS
