"""
write 도구 (apply patch / commit / push) — Dev Manager Phase 2.

PRD: docs/prd/dev-relay-write-tools.md (AC-WT-2 ~ AC-WT-6, AC-WT-13)

설계 원칙
- write 도구는 모두 **사용자 명시 명령 + 2단계 confirm** 통과 후에만 워킹트리·로컬
  커밋·remote 에 영향을 준다.
- patch 적용은 `git apply --check` 로 검증 후 적용. 실패 시 워킹트리 미변경.
- commit 은 staged 변경이 있어야 진행. 빈 트리 commit 차단.
- push 는 현재 브랜치 fast-forward push 만. force 류는 가드가 사전 차단.
- 모든 외부 노출 텍스트 (자동 커밋 메시지 등) 는 발사 직전 컴플라이언스 가드 통과.

본 모듈은 SDK 자체를 직접 호출하지 않는다 — patch / 커밋 메시지 생성 callable
은 호출 측 (`write_runtime`) 이 주입한다 (테스트 가능성 + SDK 미설정 환경 호환).
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from ai.coordinator._compliance import find_forbidden_keywords


# patch 본문 안에서 destructive 표지를 검출하기 위한 정규식.
# `rm -rf /`, `> /dev/null` 류, force push 표지 등 — 정상 unified diff 본문에는
# 등장하지 않을 표지를 보수적으로 막는다.
_PATCH_DESTRUCTIVE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"rm\s+-rf\s+/", re.IGNORECASE),
    re.compile(r">\s*/dev/", re.IGNORECASE),
    re.compile(r"push\s+--force", re.IGNORECASE),
    re.compile(r"force\s*push", re.IGNORECASE),
    re.compile(r"reset\s+--hard", re.IGNORECASE),
    re.compile(r"filter-branch", re.IGNORECASE),
    re.compile(r"update-ref", re.IGNORECASE),
)

# patch 적용 대상으로 허용하지 않는 경로 패턴 (secrets / git 내부 등).
_FORBIDDEN_PATH_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(^|/)\.env(\.[^/]*)?$"),
    re.compile(r"(^|/)\.git/"),
    re.compile(r"(^|/)secrets/"),
    re.compile(r"\.key$"),
    re.compile(r"\.pem$"),
    re.compile(r"credentials", re.IGNORECASE),
)


class WriteToolError(RuntimeError):
    """write 도구가 destructive·정책 위반·실패를 검출했을 때 raise."""


class PatchDestructiveBlocked(WriteToolError):
    """patch 본문 또는 적용 대상 경로가 destructive 표지를 포함."""


class CommitMessageBlocked(WriteToolError):
    """자동 생성된 커밋 메시지가 컴플라이언스 가드 위반."""


class PushPolicyBlocked(WriteToolError):
    """push 옵션이 정책 위반 (force / branch delete 등)."""


@dataclass(frozen=True, slots=True)
class PatchPreview:
    """patch dry-run 결과 — confirm 메시지에 표시."""

    files: tuple[str, ...]
    lines_added: int
    lines_removed: int
    raw_patch: str


@dataclass(frozen=True, slots=True)
class CommitPreview:
    """commit dry-run 결과 — confirm 메시지에 표시."""

    message: str
    staged_files: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PushPreview:
    """push dry-run 결과 — confirm 메시지에 표시."""

    branch: str
    remote: str
    commit_shas: tuple[str, ...]


# ---------------------------------------------------------------------------
# Patch — destructive 검증 + dry-run 미리 보기 + 적용
# ---------------------------------------------------------------------------


def _extract_patch_target_paths(patch_text: str) -> list[str]:
    """unified diff 본문에서 변경 대상 경로 목록을 추출한다.

    `+++ b/<path>` 라인 우선. `+++ /dev/null` (파일 삭제) 인 경우만 `--- a/<path>`
    fallback. 중복은 첫 등장만 보존.
    """
    paths: list[str] = []
    pending_minus: str | None = None
    for line in patch_text.splitlines():
        if line.startswith("--- "):
            tail = line[4:].strip()
            if tail.startswith("a/"):
                tail = tail[2:]
            pending_minus = tail if tail and tail != "/dev/null" else None
        elif line.startswith("+++ "):
            tail = line[4:].strip()
            if tail.startswith("b/"):
                tail = tail[2:]
            if tail and tail != "/dev/null":
                if tail not in paths:
                    paths.append(tail)
            elif pending_minus is not None and pending_minus not in paths:
                # 파일 삭제 케이스 — `--- a/X` `+++ /dev/null`.
                paths.append(pending_minus)
            pending_minus = None
    return paths


def _count_patch_lines(patch_text: str) -> tuple[int, int]:
    """unified diff 본문에서 +/- 라인 수를 센다. `+++`/`---` 헤더는 제외."""
    added = 0
    removed = 0
    for line in patch_text.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            added += 1
        elif line.startswith("-"):
            removed += 1
    return added, removed


def check_patch_destructive(patch_text: str) -> None:
    """patch 본문에 destructive 표지가 없는지 검사.

    위반 시 `PatchDestructiveBlocked` raise — 호출 측이 audit + 사용자 안내.
    """
    if not patch_text:
        raise PatchDestructiveBlocked("patch_empty")
    for pattern in _PATCH_DESTRUCTIVE_PATTERNS:
        if pattern.search(patch_text):
            raise PatchDestructiveBlocked(
                f"destructive_marker: {pattern.pattern}"
            )
    for path in _extract_patch_target_paths(patch_text):
        for pattern in _FORBIDDEN_PATH_PATTERNS:
            if pattern.search(path):
                raise PatchDestructiveBlocked(
                    f"forbidden_path: {pattern.pattern}"
                )


def preview_patch(patch_text: str) -> PatchPreview:
    """patch 본문에서 dry-run 미리 보기를 구성.

    destructive 검증을 먼저 수행하고 통과한 경우에만 preview 반환.
    """
    check_patch_destructive(patch_text)
    paths = _extract_patch_target_paths(patch_text)
    added, removed = _count_patch_lines(patch_text)
    return PatchPreview(
        files=tuple(paths),
        lines_added=added,
        lines_removed=removed,
        raw_patch=patch_text,
    )


def apply_patch(
    patch_text: str,
    *,
    cwd: Path | str | None = None,
    runner: Callable[..., subprocess.CompletedProcess] | None = None,
) -> tuple[str, ...]:
    """unified diff 본문을 워킹트리에 적용.

    동작 순서:
    1. `check_patch_destructive` — 본문·경로 destructive 검증.
    2. `git apply --check` — 적용 가능 여부 검증 (실패 시 워킹트리 미변경).
    3. `git apply` — 실제 적용.

    반환: 적용된 파일 목록 tuple (audit `patch_applied.files` 에 그대로 들어감).

    PR #54 reviewer P1 #1 — `cwd` 는 데몬 시작 디렉터리 의존을 피하기 위해 호출
    측이 명시 전달하도록 권장. runner 가 주입된 테스트 경로에서는 cwd 미주입을
    허용 (mock subprocess 가 cwd 를 참조하지 않음).
    """
    check_patch_destructive(patch_text)

    if shutil.which("git") is None:
        raise WriteToolError("git_not_found")

    _runner = runner or subprocess.run
    if cwd is None and runner is None:
        raise WriteToolError("cwd_required")
    cwd_str = str(cwd) if cwd is not None else None

    check_result = _runner(
        ["git", "apply", "--check", "-"],
        input=patch_text,
        text=True,
        capture_output=True,
        cwd=cwd_str,
        check=False,
    )
    if check_result.returncode != 0:
        stderr = (check_result.stderr or "").strip()[:200]
        raise WriteToolError(f"patch_apply_failed: {stderr}")

    apply_result = _runner(
        ["git", "apply", "-"],
        input=patch_text,
        text=True,
        capture_output=True,
        cwd=cwd_str,
        check=False,
    )
    if apply_result.returncode != 0:
        stderr = (apply_result.stderr or "").strip()[:200]
        raise WriteToolError(f"patch_apply_failed: {stderr}")

    return tuple(_extract_patch_target_paths(patch_text))


# ---------------------------------------------------------------------------
# Commit — 메시지 가드 + dry-run + 커밋
# ---------------------------------------------------------------------------


# 커밋 메시지에 절대 포함되면 안 되는 표지 — `--amend`, `--no-verify` 등.
_COMMIT_FORBIDDEN_FLAGS: tuple[str, ...] = (
    "--amend",
    "--no-verify",
    "--reset-author",
    "-S",  # gpg sign override (정확 토큰 비교, 부분 매치 아님)
)


def check_commit_message(message: str) -> None:
    """자동 생성된 커밋 메시지의 컴플라이언스 + destructive 표지 검사.

    위반 시 `CommitMessageBlocked` raise.
    """
    if not message or not message.strip():
        raise CommitMessageBlocked("empty_message")
    matched = find_forbidden_keywords(message)
    if matched:
        raise CommitMessageBlocked(f"compliance: {sorted(matched)}")
    lowered_tokens = set(message.lower().split())
    for flag in _COMMIT_FORBIDDEN_FLAGS:
        if flag in lowered_tokens:
            raise CommitMessageBlocked(f"forbidden_flag: {flag}")


def _staged_files(
    *,
    cwd: Path | str | None,
    runner: Callable[..., subprocess.CompletedProcess],
) -> tuple[str, ...]:
    cwd_str = str(cwd) if cwd is not None else None
    result = runner(
        ["git", "diff", "--cached", "--name-only"],
        text=True,
        capture_output=True,
        cwd=cwd_str,
        check=False,
    )
    if result.returncode != 0:
        return tuple()
    return tuple(
        line.strip()
        for line in (result.stdout or "").splitlines()
        if line.strip()
    )


def preview_commit(
    message: str,
    *,
    cwd: Path | str | None = None,
    runner: Callable[..., subprocess.CompletedProcess] | None = None,
    auto_stage: bool = True,
) -> CommitPreview:
    """commit dry-run 미리 보기.

    `auto_stage=True` 면 워킹트리의 unstaged 변경을 `git add -A` 로 staging 한 뒤
    검사한다 (apply patch 직후 흐름). 호출 측이 `False` 로 두면 이미 staged 변경
    만 본다.

    PR #54 reviewer P1 #1 — `cwd` 는 호출 측 명시 전달 권장. runner 미주입 (실
    subprocess 호출) 경로에서는 cwd 누락 시 `cwd_required` 분류로 거절.
    """
    check_commit_message(message)

    if shutil.which("git") is None:
        raise WriteToolError("git_not_found")
    _runner = runner or subprocess.run
    if cwd is None and runner is None:
        raise WriteToolError("cwd_required")
    cwd_str = str(cwd) if cwd is not None else None

    if auto_stage:
        _runner(
            ["git", "add", "-A"],
            text=True,
            capture_output=True,
            cwd=cwd_str,
            check=False,
        )

    staged = _staged_files(cwd=cwd, runner=_runner)
    if not staged:
        raise WriteToolError("commit_empty_tree")

    return CommitPreview(message=message, staged_files=staged)


def perform_commit(
    message: str,
    *,
    cwd: Path | str | None = None,
    runner: Callable[..., subprocess.CompletedProcess] | None = None,
) -> str:
    """`git commit -m <message>` 수행 후 SHA 반환.

    호출 시점에 staged 변경이 있다는 가정 (`preview_commit` 이 보장).

    PR #54 reviewer P1 #1 — `cwd` 는 호출 측 명시 전달 권장. runner 미주입 (실
    subprocess 호출) 경로에서는 cwd 누락 시 `cwd_required` 분류로 거절.
    """
    check_commit_message(message)
    if shutil.which("git") is None:
        raise WriteToolError("git_not_found")
    _runner = runner or subprocess.run
    if cwd is None and runner is None:
        raise WriteToolError("cwd_required")
    cwd_str = str(cwd) if cwd is not None else None

    result = _runner(
        ["git", "commit", "-m", message],
        text=True,
        capture_output=True,
        cwd=cwd_str,
        check=False,
    )
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()[:200]
        if "nothing to commit" in (result.stderr or "").lower():
            raise WriteToolError("commit_empty_tree")
        raise WriteToolError(f"commit_failed: {stderr}")

    rev_result = _runner(
        ["git", "rev-parse", "HEAD"],
        text=True,
        capture_output=True,
        cwd=cwd_str,
        check=False,
    )
    sha = (rev_result.stdout or "").strip() if rev_result.returncode == 0 else ""
    return sha[:12] if sha else ""


# ---------------------------------------------------------------------------
# Push — 정책 검증 + dry-run + push
# ---------------------------------------------------------------------------


# push 시 화이트리스트 된 옵션. 그 외 옵션은 거부.
_ALLOWED_PUSH_OPTS: frozenset[str] = frozenset(
    {"--set-upstream", "-u"}
)

# push 가 절대 허용되지 않는 브랜치 (직접 push 금지).
_PROTECTED_BRANCHES: frozenset[str] = frozenset(
    {"main", "master", "develop", "release"}
)


def _current_branch(
    *,
    cwd: Path | str | None,
    runner: Callable[..., subprocess.CompletedProcess],
) -> str:
    cwd_str = str(cwd) if cwd is not None else None
    result = runner(
        ["git", "branch", "--show-current"],
        text=True,
        capture_output=True,
        cwd=cwd_str,
        check=False,
    )
    if result.returncode != 0:
        return ""
    return (result.stdout or "").strip()


def _commits_to_push(
    branch: str,
    remote: str,
    *,
    cwd: Path | str | None,
    runner: Callable[..., subprocess.CompletedProcess],
) -> tuple[str, ...]:
    cwd_str = str(cwd) if cwd is not None else None
    spec = f"{remote}/{branch}..HEAD"
    result = runner(
        ["git", "log", "--pretty=%h", spec],
        text=True,
        capture_output=True,
        cwd=cwd_str,
        check=False,
    )
    if result.returncode != 0:
        # remote tracking 이 없을 수도 있음 — HEAD ~5 로 fallback.
        fallback = runner(
            ["git", "log", "--pretty=%h", "-n", "5"],
            text=True,
            capture_output=True,
            cwd=cwd_str,
            check=False,
        )
        if fallback.returncode != 0:
            return tuple()
        return tuple(
            line.strip()
            for line in (fallback.stdout or "").splitlines()
            if line.strip()
        )
    return tuple(
        line.strip()
        for line in (result.stdout or "").splitlines()
        if line.strip()
    )


def check_push_policy(
    branch: str,
    *,
    extra_opts: Iterable[str] = (),
) -> None:
    """push 옵션·브랜치 정책 검증.

    위반 시 `PushPolicyBlocked` raise.
    """
    if not branch or not branch.strip():
        raise PushPolicyBlocked("empty_branch")
    if branch in _PROTECTED_BRANCHES:
        raise PushPolicyBlocked(f"protected_branch: {branch}")
    for opt in extra_opts:
        if opt not in _ALLOWED_PUSH_OPTS:
            raise PushPolicyBlocked(f"forbidden_opt: {opt}")


def preview_push(
    *,
    cwd: Path | str | None = None,
    remote: str = "origin",
    runner: Callable[..., subprocess.CompletedProcess] | None = None,
) -> PushPreview:
    """push dry-run 미리 보기.

    현재 브랜치 + push 될 커밋 SHA 목록을 수집.

    PR #54 reviewer P1 #1 — `cwd` 는 호출 측 명시 전달 권장. runner 미주입 (실
    subprocess 호출) 경로에서는 cwd 누락 시 `cwd_required` 분류로 거절.
    """
    if shutil.which("git") is None:
        raise WriteToolError("git_not_found")
    _runner = runner or subprocess.run
    if cwd is None and runner is None:
        raise WriteToolError("cwd_required")
    branch = _current_branch(cwd=cwd, runner=_runner)
    check_push_policy(branch)
    commits = _commits_to_push(branch, remote, cwd=cwd, runner=_runner)
    return PushPreview(branch=branch, remote=remote, commit_shas=commits)


def perform_push(
    *,
    cwd: Path | str | None = None,
    remote: str = "origin",
    runner: Callable[..., subprocess.CompletedProcess] | None = None,
) -> tuple[str, str]:
    """`git push <remote> <branch>` 수행. (remote, branch) 반환.

    push 가 거절되거나 timeout 이면 `WriteToolError` raise.

    PR #54 reviewer P1 #1 — `cwd` 는 호출 측 명시 전달 권장. runner 미주입 (실
    subprocess 호출) 경로에서는 cwd 누락 시 `cwd_required` 분류로 거절.
    """
    if shutil.which("git") is None:
        raise WriteToolError("git_not_found")
    _runner = runner or subprocess.run
    if cwd is None and runner is None:
        raise WriteToolError("cwd_required")
    branch = _current_branch(cwd=cwd, runner=_runner)
    check_push_policy(branch)
    cwd_str = str(cwd) if cwd is not None else None
    result = _runner(
        ["git", "push", remote, branch],
        text=True,
        capture_output=True,
        cwd=cwd_str,
        check=False,
        timeout=60.0,
    )
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()[:200].lower()
        if "non-fast-forward" in stderr or "rejected" in stderr:
            raise WriteToolError(f"push_rejected: {stderr[:120]}")
        raise WriteToolError(f"push_failed: {stderr[:120]}")
    return remote, branch


__all__ = [
    "CommitMessageBlocked",
    "CommitPreview",
    "PatchDestructiveBlocked",
    "PatchPreview",
    "PushPolicyBlocked",
    "PushPreview",
    "WriteToolError",
    "apply_patch",
    "check_commit_message",
    "check_patch_destructive",
    "check_push_policy",
    "perform_commit",
    "perform_push",
    "preview_commit",
    "preview_patch",
    "preview_push",
]
