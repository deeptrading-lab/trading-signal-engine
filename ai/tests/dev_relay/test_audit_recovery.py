"""audit.jsonl 기반 머지 carve-out 식별 단위 테스트.

PRD `dev-relay-agent-integration.md` §3.1.
"""

from __future__ import annotations

import json
from pathlib import Path

from ai.dev_relay.audit_recovery import find_merge_in_flight_job_ids


def _write_audit(path: Path, lines: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for record in lines:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


class TestFindMergeInFlightJobIds:
    def test_missing_file_returns_empty(self, tmp_path: Path):
        assert find_merge_in_flight_job_ids(tmp_path / "no.jsonl") == frozenset()

    def test_started_without_terminal_is_in_flight(self, tmp_path: Path):
        path = tmp_path / "audit.jsonl"
        _write_audit(
            path,
            [
                {"ts": "x", "kind": "merge_started", "job_id": 7, "pr": 22},
            ],
        )
        assert find_merge_in_flight_job_ids(path) == frozenset({7})

    def test_started_then_done_not_in_flight(self, tmp_path: Path):
        path = tmp_path / "audit.jsonl"
        _write_audit(
            path,
            [
                {"ts": "x", "kind": "merge_started", "job_id": 7, "pr": 22},
                {"ts": "y", "kind": "merge_done", "job_id": 7, "pr": 22, "sha": "abc"},
            ],
        )
        assert find_merge_in_flight_job_ids(path) == frozenset()

    def test_started_then_failed_not_in_flight(self, tmp_path: Path):
        path = tmp_path / "audit.jsonl"
        _write_audit(
            path,
            [
                {"ts": "x", "kind": "merge_started", "job_id": 7, "pr": 22},
                {"ts": "y", "kind": "merge_failed", "job_id": 7, "pr": 22},
            ],
        )
        assert find_merge_in_flight_job_ids(path) == frozenset()

    def test_multiple_jobs_mixed(self, tmp_path: Path):
        path = tmp_path / "audit.jsonl"
        _write_audit(
            path,
            [
                {"ts": "x", "kind": "merge_started", "job_id": 1, "pr": 11},
                {"ts": "x", "kind": "merge_started", "job_id": 2, "pr": 12},
                {"ts": "x", "kind": "merge_done", "job_id": 1, "pr": 11, "sha": "a"},
                {"ts": "x", "kind": "merge_started", "job_id": 3, "pr": 13},
            ],
        )
        assert find_merge_in_flight_job_ids(path) == frozenset({2, 3})

    def test_corrupt_lines_skipped(self, tmp_path: Path):
        path = tmp_path / "audit.jsonl"
        path.write_text(
            '{"ts": "x", "kind": "merge_started", "job_id": 7, "pr": 22}\n'
            "this is not json\n"
            '{"ts": "y", "kind": "merge_done", "job_id": 7, "pr": 22}\n',
            encoding="utf-8",
        )
        assert find_merge_in_flight_job_ids(path) == frozenset()

    def test_unrelated_kinds_ignored(self, tmp_path: Path):
        path = tmp_path / "audit.jsonl"
        _write_audit(
            path,
            [
                {"ts": "x", "kind": "command_received", "job_id": 1},
                {"ts": "x", "kind": "reviewer_started", "job_id": 1},
                {"ts": "x", "kind": "reviewer_done", "job_id": 1},
            ],
        )
        assert find_merge_in_flight_job_ids(path) == frozenset()
