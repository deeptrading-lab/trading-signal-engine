"""
명령 응답 텍스트 생성.

PRD AC-2, AC-3, AC-4 — `ping`/`status`/fallback.
외부 노출 텍스트에는 도메인 키워드를 포함하지 않는다 — 정확한 정책 목록은
`ai.coordinator._compliance.FORBIDDEN_KEYWORDS` 단일 정의 지점을 참조한다.
봇 자기 지칭은 "코디네이터" 표현 사용.
"""

from __future__ import annotations

import platform
import socket
import time
from datetime import datetime, timezone, timedelta
from typing import Callable

# KST 타임존 — `zoneinfo` 미가용 환경(데이터 미설치)에서도 동작하도록 고정 오프셋 사용.
KST = timezone(timedelta(hours=9), name="KST")

# 시작 시각 — 모듈 import 시점 기준. 데몬 entrypoint 가 단일 프로세스이므로
# 충분히 의미 있는 가동시간 기준이 된다.
_PROCESS_START_MONOTONIC = time.monotonic()


def _format_uptime(seconds: float) -> str:
    """`Nd HH:MM:SS` 형식. AC-3 의 사람이 읽을 수 있는 형식 요구."""
    total = int(seconds)
    days, rem = divmod(total, 86_400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{days}d {hours:02d}:{minutes:02d}:{secs:02d}"


def _format_now_kst(now: datetime | None = None) -> str:
    """현재 시각을 KST ISO-8601 로. 테스트 주입을 위해 인자 허용."""
    current = now if now is not None else datetime.now(tz=KST)
    if current.tzinfo is None:
        current = current.replace(tzinfo=KST)
    else:
        current = current.astimezone(KST)
    return current.isoformat(timespec="seconds")


def render_ping() -> str:
    """AC-2: `ping` → `pong`."""
    return "pong"


def render_status(
    *,
    now_provider: Callable[[], datetime] | None = None,
    monotonic_provider: Callable[[], float] | None = None,
    hostname_provider: Callable[[], str] | None = None,
    python_version_provider: Callable[[], str] | None = None,
    process_start_monotonic: float | None = None,
) -> str:
    """
    AC-3: 가동시간·호스트명·현재 시각(KST ISO-8601)·Python 버전 4종을 포함.

    의존성 주입 인자는 단위 테스트용. 실제 호출 시 모두 None 으로 두면
    표준 라이브러리 값을 사용한다.
    """
    monotonic_fn = monotonic_provider or time.monotonic
    start = (
        process_start_monotonic
        if process_start_monotonic is not None
        else _PROCESS_START_MONOTONIC
    )
    uptime = _format_uptime(monotonic_fn() - start)

    hostname = (hostname_provider or socket.gethostname)()
    now_dt = (now_provider or (lambda: datetime.now(tz=KST)))()
    current_iso = _format_now_kst(now_dt)
    py_version = (python_version_provider or platform.python_version)()

    lines = [
        "코디네이터 상태",
        f"- 가동시간: {uptime}",
        f"- 호스트명: {hostname}",
        f"- 현재 시각(KST): {current_iso}",
        f"- Python: {py_version}",
    ]
    return "\n".join(lines)


def render_fallback() -> str:
    """AC-4: 알 수 없는 입력 → 사용 가능한 명령 안내."""
    return (
        "사용 가능한 명령은 다음과 같습니다.\n"
        "- ping: 헬스 체크 응답\n"
        "- status: 코디네이터 가동 상태 요약"
    )


def normalize_command(text: str | None) -> str:
    """입력 트림·소문자 정규화 (AC-4)."""
    if text is None:
        return ""
    return text.strip().lower()


def route_command(text: str | None) -> str:
    """
    정규화된 명령을 응답 텍스트로 매핑. 알 수 없으면 fallback.

    AC-2/AC-3/AC-4 의 라우팅 진입점. 단위 테스트는 본 함수와
    `render_*` 들을 직접 호출한다.
    """
    command = normalize_command(text)
    if command == "ping":
        return render_ping()
    if command == "status":
        return render_status()
    return render_fallback()
