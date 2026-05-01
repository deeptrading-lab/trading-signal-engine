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
    DESTRUCTIVE_BLOCKED = "destructive_blocked"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ParsedCommand:
    """파싱된 명령 기술."""

    kind: CommandKind
    raw: str  # 원본 입력 (앞뒤 공백 trim 한 형태)
    normalized: str  # 정규화된 명령 문자열 (예: "review pr 22")
    pr_number: int | None = None


# Destructive 표지 — 입력 raw 텍스트(소문자) 안에 부분 문자열로 등장하면 차단.
# AC-13: `git reset --hard`, `git push --force`, `branch -D`, `clean -f` 등.
# 추가로 흔한 머지/리베이스 우회 표현도 막는다.
_DESTRUCTIVE_PATTERNS: tuple[str, ...] = (
    "reset --hard",
    "push --force",
    "push -f",
    "force push",
    "force-push",
    "branch -d",
    "clean -f",
    "clean -fd",
    "rebase --hard",
    "checkout --",
    "restore --",
    "filter-branch",
    "update-ref",
)


_REVIEW_PR_RE = re.compile(r"^review\s+pr\s+(\d+)$")
_MERGE_PR_RE = re.compile(r"^merge\s+pr\s+(\d+)$")


def normalize(text: str | None) -> str:
    """입력 트림·소문자·공백 압축."""
    if text is None:
        return ""
    return re.sub(r"\s+", " ", text.strip().lower())


def is_destructive(text: str | None) -> bool:
    """destructive op 표지가 입력에 포함되어 있는지 (AC-13 1차 차단).

    부분 문자열 매치 기반. 라우팅 단에서 unknown 으로 떨어뜨리고 별도 안내를
    덧붙이기 위한 용도.
    """
    if not text:
        return False
    needle = text.lower()
    return any(p in needle for p in _DESTRUCTIVE_PATTERNS)


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

    return ParsedCommand(
        kind=CommandKind.UNKNOWN,
        raw=raw_trimmed,
        normalized=normalized,
    )
