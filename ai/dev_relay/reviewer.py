"""
reviewer 에이전트 호출 (Dev Manager — agent integration).

PRD `dev-relay-agent-integration.md` §3.2:
- `review pr <N>` job 이 picker 에 의해 dequeue 되면 본 모듈이 실행된다.
- Claude Agent SDK 신규 세션 (NL 분기 세션과 분리) 으로 PR diff + 리뷰
  instruction 을 prompt 로 전달한다.
- 결과는 `ReviewResult` (요약 + 발견 사항 최대 3건 + 본문 detail) — Slack 발사
  자체는 호출 측 (`main`) 책임.

본 모듈은 SDK 자체를 직접 호출하지 않는다. 호출 측이 `ReviewerCallable` 을 주입
한다 (테스트 가능성 + 환경 미설정 환경 호환). 실제 SDK 호출은 `nl_sdk_runtime`
패턴을 그대로 재사용해 `main._build_reviewer` 가 만든다.

상세 보기 (PRD §3.2) 캐시는 in-memory + 데몬 lifetime 한정 — 데몬 재시작 시
유실되며, 그 경우 `TEMPLATE_REVIEW_DETAIL_LOOKUP_FAILED` 안내 + audit 1라인.
"""

from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from dataclasses import dataclass
from typing import Callable

_LOGGER = logging.getLogger("ai.dev_relay.reviewer")

# 발견 사항 최대 노출 개수 (PRD §3.2).
MAX_FINDINGS_DISPLAYED: int = 3


@dataclass(frozen=True, slots=True)
class ReviewResult:
    """reviewer 호출 결과 — 동기 반환."""

    summary: str  # 2~3 문장.
    findings: list[str]  # 0개 이상. 표시는 상위 3개만.
    detail: str  # `[상세 보기]` 클릭 시 발사할 본문.


# 호출 측이 주입하는 SDK 호출 callable.
# `pr_number` 와 PR diff 텍스트(또는 fetch 함수가 만들어낸 컨텍스트) 를 받아
# `ReviewResult` 를 반환한다.
ReviewerCallable = Callable[[int], ReviewResult]


class ReviewDetailCache:
    """`[상세 보기]` 본문 lookup 용 in-memory LRU 캐시.

    PRD §3.2 — Slack `value` 필드에 큰 본문을 넣을 수 없으므로 캐시 키 = job_id.
    데몬 lifetime 한정이며 재시작 시 유실된다 (의도된 동작 — 사용자가 다시
    `review pr <N>` 을 입력하면 새 결과가 캐시된다).
    """

    def __init__(self, *, max_entries: int = 128) -> None:
        if max_entries < 1:
            raise ValueError("max_entries 는 1 이상이어야 합니다.")
        self._max = max_entries
        self._store: OrderedDict[int, str] = OrderedDict()
        self._lock = threading.Lock()

    def put(self, job_id: int, detail: str) -> None:
        with self._lock:
            if job_id in self._store:
                self._store.move_to_end(job_id)
            self._store[job_id] = detail
            while len(self._store) > self._max:
                self._store.popitem(last=False)

    def get(self, job_id: int) -> str | None:
        with self._lock:
            value = self._store.get(job_id)
            if value is not None:
                self._store.move_to_end(job_id)
            return value


def truncate_findings(findings: list[str]) -> list[str]:
    """노출 시 상위 N건만 잘라낸다. 빈 입력은 빈 리스트 그대로."""
    return findings[:MAX_FINDINGS_DISPLAYED]


__all__ = [
    "MAX_FINDINGS_DISPLAYED",
    "ReviewDetailCache",
    "ReviewResult",
    "ReviewerCallable",
    "truncate_findings",
]
