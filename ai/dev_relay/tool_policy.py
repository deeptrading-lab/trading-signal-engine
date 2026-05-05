"""
SDK PreToolUse hook 정책 (Dev Manager 자연어 분기, Phase 1 read-only).

PRD: docs/prd/dev-relay-natural-language.md §3.4 / AC-9 ~ AC-14, AC-16

설계
- Phase 1 은 **read-only**. write 도구 (`Edit`, `Write`) 는 일체 거부.
- `Bash` 는 read-only 화이트리스트로 한정. mutating 명령은 모두 거부.
- `Read` 는 비밀 파일 패턴 (`.env*`, `secrets/*`, `*token*`, `*credential*`) 거부.
- `WebFetch` 는 도메인 화이트리스트 (`web_allowlist`) 통과만 허용.
- 본 모듈은 *순수 함수* 만 노출. SDK 호출은 호출 측 (agent_runner) 책임.

PRD §3.7 audit log 신규 kind:
- `tool_call` — 허용된 도구 호출.
- `tool_denied` — 거부된 도구 호출.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass

from ai.dev_relay.dispatcher import is_destructive
from ai.dev_relay.web_allowlist import is_allowed as is_url_allowed


# ---------------------------------------------------------------------------
# 결정 결과
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ToolDecision:
    """PreToolUse 정책 평가 결과.

    - allowed: True 면 도구 호출을 통과시킨다.
    - reason: 거부 사유 식별자 (audit log 의 `reason` 필드로 그대로 기록).
      허용 시 None.
    - brief: audit log 에 기록할 짧은 도구 호출 요약 (전체 인자 노출 없이).
    """

    allowed: bool
    reason: str | None
    brief: str


# ---------------------------------------------------------------------------
# Read 정책 — 비밀 파일 패턴 거부
# ---------------------------------------------------------------------------

# PRD §3.4 — 비밀 파일 패턴.
# 단순화를 위해 정규식 단일 패턴으로 합성. 경로 구분자 `/` 만 가정.
_SECRET_PATH_PATTERNS: tuple[re.Pattern[str], ...] = (
    # `.env`, `.env.local`, `.envrc` 등.
    re.compile(r"(^|/)\.env(\.[^/]*)?$"),
    # `secrets/` 하위 모든 파일.
    re.compile(r"(^|/)secrets/"),
    # 파일명에 `token`, `credential` 이 들어간 경우.
    re.compile(r"[^/]*token[^/]*$", re.IGNORECASE),
    re.compile(r"[^/]*credential[^/]*$", re.IGNORECASE),
)


def _is_secret_path(path: str) -> bool:
    if not path:
        return False
    return any(p.search(path) for p in _SECRET_PATH_PATTERNS)


# ---------------------------------------------------------------------------
# Bash 정책 — read-only 화이트리스트
# ---------------------------------------------------------------------------

# 첫 토큰 (실행 바이너리) 기준 read-only 허용 목록.
# git/gh 는 sub-command 까지 검사한다.
_READONLY_BASH_HEAD: frozenset[str] = frozenset(
    {
        "cat",
        "head",
        "tail",
        "wc",
        "grep",
        "rg",
        "find",
        "ls",
        "pwd",
        "tree",
        "du",
        "stat",
    }
)

_READONLY_GIT_SUB: frozenset[str] = frozenset(
    {"log", "status", "diff", "show", "branch", "rev-parse", "config"}
)

_READONLY_GH_SUB: frozenset[tuple[str, str]] = frozenset(
    {
        ("pr", "list"),
        ("pr", "view"),
        ("issue", "list"),
        ("issue", "view"),
        ("repo", "view"),
        ("auth", "status"),
    }
)

# pytest 는 `--collect-only` 만 허용 (다른 옵션은 실 테스트 실행 — 사이드이펙트 발생).
_PYTEST_READONLY_FLAG = "--collect-only"

# mutating 표지 — 첫 토큰 또는 sub-command. 부분 문자열 검사 1차 필터.
_MUTATING_HEADS: frozenset[str] = frozenset(
    {
        "rm",
        "mv",
        "cp",
        "mkdir",
        "touch",
        "chmod",
        "chown",
        "ln",
        "tee",
        "dd",
        "npm",
        "pip",
        "pip3",
        "yarn",
        "make",
        "python",
        "python3",
        "sh",
        "bash",
        "zsh",
        "node",
        "ruby",
        "perl",
    }
)

# git/gh 의 mutating sub-command — 화이트리스트 외 모두 거부지만, 명시적으로 표기.
_MUTATING_GIT_SUB: frozenset[str] = frozenset(
    {
        "commit",
        "push",
        "pull",
        "merge",
        "rebase",
        "reset",
        "checkout",
        "restore",
        "stash",
        "clean",
        "add",
        "rm",
        "mv",
        "tag",
        "fetch",
        "fork",
    }
)

_MUTATING_GH_VERBS: frozenset[str] = frozenset(
    {"create", "edit", "close", "merge", "delete", "approve", "review"}
)

# redirect / pipe-mutation 표지 — shell metacharacter.
_FORBIDDEN_SHELL_METACHARS: tuple[str, ...] = (
    ">",  # output redirect
    ">>",
    "<",  # input redirect (테스트 격리 측면에서도 거부)
    "|",  # pipe — read-only 명령만 통과시키기 어려우므로 보수적으로 거부
    "&",  # background / 명령 chain
    ";",  # 명령 chain
    "`",  # command substitution
    "$(",  # command substitution
)


def _looks_mutating(command: str) -> bool:
    """mutating 표지가 명령어 raw 텍스트에 포함되어 있는지."""
    lowered = command.lower()
    if any(token in lowered for token in _FORBIDDEN_SHELL_METACHARS):
        return True
    return False


def _evaluate_bash(command: str) -> ToolDecision:
    """`Bash` 명령어를 read-only 화이트리스트 정책으로 평가."""
    raw = (command or "").strip()
    brief = _bash_brief(raw)

    if not raw:
        return ToolDecision(allowed=False, reason="empty_command", brief=brief)

    # destructive 표지 (`reset --hard`, `push --force` 등) 1차 차단.
    if is_destructive(raw):
        return ToolDecision(allowed=False, reason="destructive_command", brief=brief)

    # shell metachar 가 들어간 복합 명령은 화이트리스트 회피 가능 — 거부.
    if _looks_mutating(raw):
        return ToolDecision(allowed=False, reason="mutating_command", brief=brief)

    try:
        tokens = shlex.split(raw)
    except ValueError:
        return ToolDecision(allowed=False, reason="parse_error", brief=brief)
    if not tokens:
        return ToolDecision(allowed=False, reason="empty_command", brief=brief)

    head = tokens[0]

    # 명시적 mutating head 거부.
    if head in _MUTATING_HEADS:
        return ToolDecision(allowed=False, reason="mutating_command", brief=brief)

    # `find` 의 mutating flag 거부 (`-delete`, `-exec`).
    if head == "find":
        if "-delete" in tokens or "-exec" in tokens or "-execdir" in tokens:
            return ToolDecision(
                allowed=False, reason="mutating_command", brief=brief
            )
        return ToolDecision(allowed=True, reason=None, brief=brief)

    if head in _READONLY_BASH_HEAD:
        return ToolDecision(allowed=True, reason=None, brief=brief)

    if head == "git":
        if len(tokens) < 2:
            return ToolDecision(allowed=False, reason="parse_error", brief=brief)
        sub = tokens[1]
        if sub in _MUTATING_GIT_SUB:
            return ToolDecision(
                allowed=False, reason="mutating_command", brief=brief
            )
        if sub in _READONLY_GIT_SUB:
            # `git branch -D` 같은 mutating flag 차단 (이미 dispatcher 의
            # destructive 표지에서 1차 잡히지만 본 모듈에서도 한 번 더).
            if sub == "branch" and any(
                flag in tokens for flag in ("-D", "-d", "--delete")
            ):
                return ToolDecision(
                    allowed=False, reason="mutating_command", brief=brief
                )
            return ToolDecision(allowed=True, reason=None, brief=brief)
        return ToolDecision(allowed=False, reason="not_whitelisted", brief=brief)

    if head == "gh":
        if len(tokens) < 3:
            return ToolDecision(allowed=False, reason="not_whitelisted", brief=brief)
        sub_pair = (tokens[1], tokens[2])
        if sub_pair in _READONLY_GH_SUB:
            return ToolDecision(allowed=True, reason=None, brief=brief)
        # 명확한 mutating verb 검출.
        if tokens[2] in _MUTATING_GH_VERBS:
            return ToolDecision(
                allowed=False, reason="mutating_command", brief=brief
            )
        return ToolDecision(allowed=False, reason="not_whitelisted", brief=brief)

    if head == "pytest":
        if _PYTEST_READONLY_FLAG in tokens:
            return ToolDecision(allowed=True, reason=None, brief=brief)
        return ToolDecision(allowed=False, reason="mutating_command", brief=brief)

    return ToolDecision(allowed=False, reason="not_whitelisted", brief=brief)


def _bash_brief(command: str) -> str:
    """audit log 에 기록할 짧은 명령 요약. 인자 일부만 보존."""
    snippet = (command or "").strip()
    if len(snippet) > 80:
        snippet = snippet[:77] + "..."
    return snippet


# ---------------------------------------------------------------------------
# 도구별 진입점
# ---------------------------------------------------------------------------


# Phase 1 허용 도구 식별자.
ALLOWED_TOOLS: frozenset[str] = frozenset(
    {"Read", "Glob", "Grep", "WebFetch", "Bash"}
)

# Phase 1 명시 거부 도구 (write 일체).
DENIED_TOOLS: frozenset[str] = frozenset({"Edit", "Write", "NotebookEdit"})


def evaluate(tool_name: str, tool_input: dict) -> ToolDecision:
    """SDK PreToolUse hook 의 정책 평가 진입점.

    호출 측 (agent_runner) 이 SDK hook callback 안에서 본 함수를 호출하고,
    `ToolDecision.allowed` 에 따라 deny/allow 응답을 SDK 에 돌려준다.
    """
    name = (tool_name or "").strip()

    if name in DENIED_TOOLS:
        return ToolDecision(
            allowed=False, reason="phase1_readonly", brief=name
        )

    if name == "Read":
        path = str((tool_input or {}).get("file_path") or "")
        brief = f"Read {path[:100]}"
        if _is_secret_path(path):
            return ToolDecision(allowed=False, reason="secret_pattern", brief=brief)
        return ToolDecision(allowed=True, reason=None, brief=brief)

    if name == "Glob":
        pattern = str((tool_input or {}).get("pattern") or "")
        return ToolDecision(allowed=True, reason=None, brief=f"Glob {pattern[:80]}")

    if name == "Grep":
        pattern = str((tool_input or {}).get("pattern") or "")
        return ToolDecision(allowed=True, reason=None, brief=f"Grep {pattern[:80]}")

    if name == "WebFetch":
        url = str((tool_input or {}).get("url") or "")
        brief = f"WebFetch {url[:100]}"
        if not is_url_allowed(url):
            return ToolDecision(
                allowed=False, reason="domain_not_allowed", brief=brief
            )
        return ToolDecision(allowed=True, reason=None, brief=brief)

    if name == "Bash":
        command = str((tool_input or {}).get("command") or "")
        return _evaluate_bash(command)

    if name not in ALLOWED_TOOLS:
        return ToolDecision(
            allowed=False, reason="not_whitelisted", brief=f"{name}"
        )

    # 안전 기본값 — 명시 화이트리스트 외 도구는 거부.
    return ToolDecision(allowed=False, reason="not_whitelisted", brief=name)


__all__ = [
    "ALLOWED_TOOLS",
    "DENIED_TOOLS",
    "ToolDecision",
    "evaluate",
]
