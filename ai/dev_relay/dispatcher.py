"""
명령 파싱·라우팅 (Dev Manager).

PRD §3.3: MVP 명령은 정확히 3개.
- `status`
- `review pr <N>`
- `merge pr <N>`

그 외 입력은 fallback (사용 가능한 명령 안내).

PRD §3.8 / AC-13: destructive git op 는 dispatcher 와 agent_runner 두 층 모두에서
차단한다. 본 모듈은 1차 차단 — 사용자가 입력한 텍스트가 destructive op 표지를
포함하면 unknown command fallback 으로 라우팅하고 별도 안내를 덧붙인다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

# PRD §3.3 — 정규화 규칙: 앞뒤 공백 trim + 대소문자 무시.
# 단, `<N>` 부분은 정수만 허용. 숫자 외 입력은 fallback.


class CommandKind(str, Enum):
    """라우팅 결과 종류."""

    STATUS = "status"
    REVIEW_PR = "review_pr"
    MERGE_PR = "merge_pr"
    # PRD `dev-relay-write-tools.md` §3.2 — write 도구 3종.
    APPLY_PATCH_PR = "apply_patch_pr"
    COMMIT_PR = "commit_pr"
    PUSH_PR = "push_pr"
    DESTRUCTIVE_BLOCKED = "destructive_blocked"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ParsedCommand:
    """파싱된 명령 기술."""

    kind: CommandKind
    raw: str  # 원본 입력 (앞뒤 공백 trim 한 형태)
    normalized: str  # 정규화된 명령 문자열 (예: "review pr 22")
    pr_number: int | None = None


# Destructive 표지 — 입력 raw 텍스트(소문자) 안에 단어 경계 기반으로 등장하면 차단.
# AC-13: `git reset --hard`, `git push --force`, `branch -D`, `clean -f` 등.
# 추가로 흔한 머지/리베이스 우회 표현도 막는다.
#
# PRD `dev-relay-write-tools.md` §3.3 — write 도구 도입으로 destructive 표면 확대.
# 다음 표지를 추가:
# - `commit --amend` / `--amend` — HEAD 재작성
# - `--no-verify` — pre-commit 우회
# - `push --mirror` / `--delete` — remote 일괄 변경
# - `push --force-with-lease` — force push 변종
# - `rm -rf` — 파일 일괄 삭제 표지 (NL 분기 진입 시 차단)
#
# PR #54 reviewer P1 #2 — flag 표지(`--force`/`--amend`/`--no-verify` 등) 는 토큰
# 경계 매치로 변경. 부분 문자열 매치(예: "amend 정책 알려줘") 가 NL 분기에서
# 의도와 다르게 차단되던 문제 해소.
#
# 매칭 정책:
# - flag-style 토큰(`--force` 등): 정규식 `\B--force\B` 가 아닌 공백 분리 토큰 동등
#   비교 또는 단어 경계. 정확한 토큰으로만 매치되도록 한다.
# - 다단어 표지(`reset --hard`, `push --force`): 정확한 부분 시퀀스 매치 (기존 동작
#   유지) — flag 단독이 아닌 명령 컨텍스트라 false-positive 위험이 낮음.
# - `rm -rf`: 시퀀스 표지 — 부분 시퀀스 매치 유지.

# 시퀀스 표지 — 부분 문자열 매치 (정상 NL 에서 등장 가능성 낮음).
_DESTRUCTIVE_SEQUENCES: tuple[str, ...] = (
    "reset --hard",
    "push --force",
    "push -f",
    "force push",
    "force-push",
    "push --mirror",
    "push --delete",
    "clean -f",
    "clean -fd",
    "rebase --hard",
    "checkout --",
    "restore --",
    "filter-branch",
    "update-ref",
    "rm -rf",
)

# `branch -d` / `branch -D` 페어 — 두 토큰 연속일 때만 차단.
_DESTRUCTIVE_TOKEN_PAIRS: tuple[tuple[str, str], ...] = (
    ("branch", "-d"),
    ("branch", "-D"),
)

# 단독 토큰으로 차단할 flag 집합 (실제 차단 대상).
_DESTRUCTIVE_SINGLE_TOKENS: frozenset[str] = frozenset(
    {
        "--force",
        "--amend",
        "--no-verify",
        "--force-with-lease",
        "--force_with_lease",
        "force-with-lease",
        "force_with_lease",
    }
)


def _tokenize_for_destructive_check(text: str) -> list[str]:
    """공백 분리 토큰화. 소문자 정규화 후 빈 토큰 제거.

    `_normalize` 가 이미 trim·소문자·공백 압축을 수행하지만 본 헬퍼는 단독으로도
    안전하게 동작하도록 보수적으로 구현.
    """
    return [t for t in re.split(r"\s+", text.lower()) if t]


_REVIEW_PR_RE = re.compile(r"^review\s+pr\s+(\d+)$")
_MERGE_PR_RE = re.compile(r"^merge\s+pr\s+(\d+)$")

# PRD `dev-relay-write-tools.md` §3.2.3 — write 도구 명령은 `pr=<N>` 인자 강제.
_APPLY_PATCH_RE = re.compile(r"^apply\s+patch\s+pr\s*=\s*(\d+)$")
_COMMIT_RE = re.compile(r"^commit\s+pr\s*=\s*(\d+)$")
_PUSH_RE = re.compile(r"^push\s+pr\s*=\s*(\d+)$")


def normalize(text: str | None) -> str:
    """입력 트림·소문자·공백 압축."""
    if text is None:
        return ""
    return re.sub(r"\s+", " ", text.strip().lower())


def is_destructive(text: str | None) -> bool:
    """destructive op 표지가 입력에 포함되어 있는지 (AC-13 1차 차단).

    매칭 정책 (PR #54 reviewer P1 #2 후속):
    - 시퀀스 표지(예: `reset --hard`, `push --force`, `rm -rf`): 부분 문자열 매치.
      정상 NL 텍스트에 등장할 가능성이 매우 낮음.
    - flag 단독 토큰(예: `--force`, `--amend`, `--no-verify`): 공백 분리 토큰
      동등 비교. 부분 문자열 매치를 쓰면 "amend 정책 알려줘" 같은 NL 이 잘못
      차단되므로 정확 토큰 매치만 인정.
    - 토큰 페어(예: `branch -d`): 두 토큰 연속일 때만 차단.

    라우팅 단에서 unknown 으로 떨어뜨리고 별도 안내를 덧붙이기 위한 용도.
    """
    if not text:
        return False
    lowered = text.lower()
    for seq in _DESTRUCTIVE_SEQUENCES:
        if seq in lowered:
            return True
    tokens = _tokenize_for_destructive_check(text)
    if not tokens:
        return False
    token_set = set(tokens)
    if token_set & _DESTRUCTIVE_SINGLE_TOKENS:
        return True
    for i in range(len(tokens) - 1):
        pair = (tokens[i], tokens[i + 1])
        if pair in _DESTRUCTIVE_TOKEN_PAIRS:
            return True
    return False


def parse(text: str | None) -> ParsedCommand:
    """입력을 ParsedCommand 로 매핑.

    매치되지 않으면 `CommandKind.UNKNOWN` 또는 `CommandKind.DESTRUCTIVE_BLOCKED`.
    """
    raw_trimmed = (text or "").strip()
    normalized = normalize(text)

    if is_destructive(text):
        return ParsedCommand(
            kind=CommandKind.DESTRUCTIVE_BLOCKED,
            raw=raw_trimmed,
            normalized=normalized,
        )

    if normalized == "status":
        return ParsedCommand(
            kind=CommandKind.STATUS,
            raw=raw_trimmed,
            normalized="status",
        )

    review_match = _REVIEW_PR_RE.match(normalized)
    if review_match:
        pr_number = int(review_match.group(1))
        return ParsedCommand(
            kind=CommandKind.REVIEW_PR,
            raw=raw_trimmed,
            normalized=f"review pr {pr_number}",
            pr_number=pr_number,
        )

    merge_match = _MERGE_PR_RE.match(normalized)
    if merge_match:
        pr_number = int(merge_match.group(1))
        return ParsedCommand(
            kind=CommandKind.MERGE_PR,
            raw=raw_trimmed,
            normalized=f"merge pr {pr_number}",
            pr_number=pr_number,
        )

    # PRD `dev-relay-write-tools.md` §3.2.3 — write 도구 3종.
    apply_match = _APPLY_PATCH_RE.match(normalized)
    if apply_match:
        pr_number = int(apply_match.group(1))
        return ParsedCommand(
            kind=CommandKind.APPLY_PATCH_PR,
            raw=raw_trimmed,
            normalized=f"apply patch pr={pr_number}",
            pr_number=pr_number,
        )

    commit_match = _COMMIT_RE.match(normalized)
    if commit_match:
        pr_number = int(commit_match.group(1))
        return ParsedCommand(
            kind=CommandKind.COMMIT_PR,
            raw=raw_trimmed,
            normalized=f"commit pr={pr_number}",
            pr_number=pr_number,
        )

    push_match = _PUSH_RE.match(normalized)
    if push_match:
        pr_number = int(push_match.group(1))
        return ParsedCommand(
            kind=CommandKind.PUSH_PR,
            raw=raw_trimmed,
            normalized=f"push pr={pr_number}",
            pr_number=pr_number,
        )

    return ParsedCommand(
        kind=CommandKind.UNKNOWN,
        raw=raw_trimmed,
        normalized=normalized,
    )
