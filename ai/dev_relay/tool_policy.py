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
# 본 상수는 단일 명령 흐름의 `_looks_mutating` 1차 필터와, pipe segment 분리 후
# segment 내부의 잔존 metachar 검사 양쪽에서 재사용된다. `|` 는 segment 분리
# 흐름이 호출 순서로 먼저 처리하므로 상수 자체에는 그대로 남긴다.
_FORBIDDEN_SHELL_METACHARS: tuple[str, ...] = (
    ">",  # output redirect
    ">>",
    "<",  # input redirect (테스트 격리 측면에서도 거부)
    "|",  # pipe — segment 분리 흐름이 우선 처리. 단일 명령 흐름에선 거부.
    "&",  # background / 명령 chain
    ";",  # 명령 chain
    "`",  # command substitution
    "$(",  # command substitution
)

# `|` 외 6종 — segment 분리 후 잔존 검사용 (PRD §3.2 단계 5).
_FORBIDDEN_NON_PIPE_METACHARS: tuple[str, ...] = tuple(
    m for m in _FORBIDDEN_SHELL_METACHARS if m != "|"
)

# DoS / 파싱 폭발 방지 — 일상 RO 조회 체인을 모두 커버하는 보수적 상한 (PRD §3.4).
_MAX_PIPE_SEGMENTS: int = 5


def _looks_mutating(command: str) -> bool:
    """mutating 표지가 명령어 raw 텍스트에 포함되어 있는지."""
    lowered = command.lower()
    if any(token in lowered for token in _FORBIDDEN_SHELL_METACHARS):
        return True
    return False


def _has_non_pipe_metachar(text: str) -> bool:
    """segment 분리 후 잔존 검사 — `|` 외 metachar 6종 부분 문자열 검출."""
    lowered = text.lower()
    return any(token in lowered for token in _FORBIDDEN_NON_PIPE_METACHARS)


def _evaluate_bash(command: str, *, depth: int = 0) -> ToolDecision:
    """`Bash` 명령어를 read-only 화이트리스트 정책으로 평가.

    `depth` 는 segment 재귀 호출 깊이 보호용 internal parameter (PRD §3.2 단계 7).
    `|` 만 segment 분리하므로 정상 흐름에서 최대 1. depth >= 1 인 호출에서 또
    segment 분기 진입 시 `parse_error` 로 fail-fast.
    """
    raw = (command or "").strip()
    brief = _bash_brief(raw)

    if not raw:
        return ToolDecision(allowed=False, reason="empty_command", brief=brief)

    # destructive 표지 (`reset --hard`, `push --force` 등) 1차 차단.
    # PRD §3.2 단계 1 — segment 분리보다 우선. `git reset --hard | echo ok` 같은
    # 입력은 segment 검증에 들어가기 전에 차단된다 (AC-PIPE-6).
    if is_destructive(raw):
        return ToolDecision(allowed=False, reason="destructive_command", brief=brief)

    # PRD §3.2 단계 2 — 토큰화. shlex 오류는 parse_error.
    try:
        tokens = shlex.split(raw)
    except ValueError:
        return ToolDecision(allowed=False, reason="parse_error", brief=brief)
    if not tokens:
        return ToolDecision(allowed=False, reason="empty_command", brief=brief)

    # PRD §3.2 단계 3 — `|` 토큰 검출. 1개 이상 있으면 segment 분리 흐름.
    if "|" in tokens:
        if depth >= 1:
            # PRD §3.2 단계 7 — 재귀 깊이 보호 fail-fast.
            return ToolDecision(allowed=False, reason="parse_error", brief=brief)
        return _evaluate_pipe_segments(tokens, brief=brief)

    # `|` 가 0개인 단일 명령 흐름 — 기존 동작 그대로 (회귀 0건 보장).
    # shell metachar 가 들어간 복합 명령은 화이트리스트 회피 가능 — 거부.
    if _looks_mutating(raw):
        return ToolDecision(allowed=False, reason="mutating_command", brief=brief)

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


def _evaluate_pipe_segments(tokens: list[str], *, brief: str) -> ToolDecision:
    """`|` 토큰 기준 segment 분할 + 각 segment 재귀 검증 (PRD §3.2 단계 4~6).

    호출 측 `_evaluate_bash` 가 `is_destructive` 1차 차단·토큰화·`|` 검출을 마친
    상태에서 호출된다. 본 함수는 다음을 책임진다.

    - segment 분할 (빈 segment → `parse_error`).
    - segment 수 상한 검사 (`_MAX_PIPE_SEGMENTS` 초과 → `parse_error`).
    - 각 segment 의 raw 텍스트에 `|` 외 metachar 6종 잔존 검사
      (`mutating_command`).
    - 각 segment 를 `_evaluate_bash(depth=1)` 로 재귀 호출. 한 segment 라도
      거부되면 그 segment 의 reason 을 그대로 전파한다.
    """
    # PRD §3.2 단계 4 — segment 분할.
    segments: list[list[str]] = []
    current: list[str] = []
    for tok in tokens:
        if tok == "|":
            if not current:
                # leading pipe / 연속 `||` 등 빈 segment 발생.
                return ToolDecision(
                    allowed=False, reason="parse_error", brief=brief
                )
            segments.append(current)
            current = []
        else:
            current.append(tok)
    if not current:
        # trailing pipe — 마지막 segment 가 비어 있음.
        return ToolDecision(allowed=False, reason="parse_error", brief=brief)
    segments.append(current)

    # PRD §3.4 — segment 수 상한.
    if len(segments) > _MAX_PIPE_SEGMENTS:
        return ToolDecision(allowed=False, reason="parse_error", brief=brief)

    # PRD §3.2 단계 5 + 6 — 각 segment 잔존 metachar 검사 + 재귀 검증.
    for seg_tokens in segments:
        # segment 의 raw 텍스트는 토큰을 공백으로 join 해 재구성. quoted token 의
        # 원본 따옴표는 유실되지만, `_has_non_pipe_metachar` / `_evaluate_bash` 는
        # 이미 토큰 단위로 검사하므로 잔존 metachar 검출에는 충분하다.
        seg_raw = " ".join(seg_tokens)
        if _has_non_pipe_metachar(seg_raw):
            return ToolDecision(
                allowed=False, reason="mutating_command", brief=brief
            )
        seg_decision = _evaluate_bash(seg_raw, depth=1)
        if not seg_decision.allowed:
            # 첫 거부 segment 의 reason 을 그대로 전파 (audit 가독성, PRD §3.3).
            return ToolDecision(
                allowed=False, reason=seg_decision.reason, brief=brief
            )

    return ToolDecision(allowed=True, reason=None, brief=brief)


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
