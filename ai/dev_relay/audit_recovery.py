"""
재시작 복구 — audit.jsonl 기반 머지 carve-out 식별 (Dev Manager).

PRD `dev-relay-agent-integration.md` §3.1:
- `merge_started` 라인은 있는데 `merge_done`/`merge_failed` 라인이 없는 job 은
  GitHub 측 머지가 이미 성사됐을 가능성이 있어 단순 `failed` 마킹 금지.
- 본 모듈은 audit.jsonl 1회 스캔으로 그 후보 job_id 집합을 산출한다.

audit.jsonl 이 없거나 손상된 경우는 빈 set 반환 — 호출 측은 종래 fallback
(`failed` 마킹) 으로 진행한다.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

_LOGGER = logging.getLogger("ai.dev_relay.audit_recovery")


_MERGE_KIND_START = "merge_started"
_MERGE_KIND_TERMINAL = frozenset({"merge_done", "merge_failed"})


def find_merge_in_flight_job_ids(audit_path: Path) -> frozenset[int]:
    """audit.jsonl 에서 carve-out 대상 job_id 집합을 산출.

    - `merge_started` 가 있으면 후보에 추가.
    - 같은 job_id 의 `merge_done` / `merge_failed` 가 뒤따르면 제거.
    - 본 함수는 데몬 시작 시 1회만 호출되며, 호출 비용은 audit 라인 수에 선형.
      MVP 기준 audit.jsonl 은 single-user / 일 단위 회전 전제라 무시 가능 수준.
    """
    if not audit_path.exists():
        return frozenset()

    started: set[int] = set()
    try:
        with audit_path.open("r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    # 손상된 라인은 건너뛴다 — 다른 정상 라인의 carve-out 식별을
                    # 막지 않기 위함.
                    continue
                if not isinstance(record, dict):
                    continue
                kind = record.get("kind")
                job_id = record.get("job_id")
                if not isinstance(kind, str) or not isinstance(job_id, int):
                    continue
                if kind == _MERGE_KIND_START:
                    started.add(job_id)
                elif kind in _MERGE_KIND_TERMINAL:
                    started.discard(job_id)
    except OSError as exc:
        _LOGGER.warning(
            "audit.jsonl 읽기 실패 (%s) — carve-out 식별 생략.",
            type(exc).__name__,
        )
        return frozenset()

    return frozenset(started)


__all__ = ["find_merge_in_flight_job_ids"]
