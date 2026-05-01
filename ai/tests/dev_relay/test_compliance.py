"""컴플라이언스 가드 단위 테스트 (PRD AC-16).

본 파일은 두 종류 검증을 수행한다.

1. **runtime 가드** — `slack_renderer.guard_text` 가 도메인 키워드를 차단하고
   안전한 fallback 으로 치환하는지.
2. **정적 검사** — `slack_renderer` 의 모든 정적 템플릿, 빌드된 Block Kit dict,
   그리고 본 PRD 와 dev_relay 소스 파일의 사용자 노출 가능 텍스트가 도메인
   키워드를 포함하지 않는지.

본 파일 자체는 fixture 로 검사 대상 키워드를 의도적으로 포함한다 (코디네이터의
`test_coordinator_compliance.py` 와 동일 예외).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from ai.coordinator._compliance import find_forbidden_keywords
from ai.dev_relay import slack_renderer


REPO_ROOT = Path(__file__).resolve().parents[3]
PRD_PATH = REPO_ROOT / "docs" / "prd" / "slack-dev-relay.md"
DEV_RELAY_DIR = REPO_ROOT / "ai" / "dev_relay"


# ---------------------------------------------------------------------------
# 1) runtime 가드 — guard_text
# ---------------------------------------------------------------------------


class TestGuardText:
    def test_clean_text_passes_through(self):
        assert slack_renderer.guard_text("안녕하세요. 응답입니다.") == "안녕하세요. 응답입니다."

    def test_empty_passes_through(self):
        assert slack_renderer.guard_text("") == ""
        assert slack_renderer.guard_text(None) == ""

    def test_blocked_text_replaced_with_fallback(self):
        # 도메인 키워드를 포함한 텍스트는 차단된다.
        bad = "test response includes signal keyword"
        assert slack_renderer.guard_text(bad) == slack_renderer.FALLBACK_RESPONSE

    def test_fallback_itself_is_clean(self):
        assert find_forbidden_keywords(slack_renderer.FALLBACK_RESPONSE) == []


# ---------------------------------------------------------------------------
# 2) 정적 템플릿 검사
# ---------------------------------------------------------------------------


_STATIC_TEMPLATES = (
    ("FALLBACK_RESPONSE", slack_renderer.FALLBACK_RESPONSE),
    ("TEMPLATE_QUEUE_ACCEPTED_REVIEW", slack_renderer.TEMPLATE_QUEUE_ACCEPTED_REVIEW),
    ("TEMPLATE_QUEUE_ACCEPTED_MERGE", slack_renderer.TEMPLATE_QUEUE_ACCEPTED_MERGE),
    ("TEMPLATE_QUEUE_BUSY", slack_renderer.TEMPLATE_QUEUE_BUSY),
    ("TEMPLATE_RECOVERY_NOTICE", slack_renderer.TEMPLATE_RECOVERY_NOTICE),
    ("TEMPLATE_CANCEL_NOTICE", slack_renderer.TEMPLATE_CANCEL_NOTICE),
    ("TEMPLATE_RATE_LIMIT", slack_renderer.TEMPLATE_RATE_LIMIT),
    ("TEMPLATE_UNKNOWN_COMMAND", slack_renderer.TEMPLATE_UNKNOWN_COMMAND),
    ("TEMPLATE_DESTRUCTIVE_BLOCKED", slack_renderer.TEMPLATE_DESTRUCTIVE_BLOCKED),
)


@pytest.mark.parametrize("name,text", _STATIC_TEMPLATES)
def test_static_template_clean(name: str, text: str):
    matched = find_forbidden_keywords(text)
    assert matched == [], f"{name} 에 도메인 키워드가 포함되어 있습니다: {matched}"


# ---------------------------------------------------------------------------
# 3) Block Kit 빌더가 만든 dict 의 모든 사용자 노출 텍스트 검사
# ---------------------------------------------------------------------------


def _walk_user_facing_text(blocks: list[dict]) -> list[str]:
    """Block Kit 트리에서 사용자 노출 가능한 텍스트 필드를 수집한다.

    `text.text`, `plain_text` value 등을 모은다. `action_id`/`block_id`/`value` 는
    내부 식별자이므로 제외 (단, `value` 는 idempotency_key 가 들어가는 경로라
    별도 검증).
    """
    collected: list[str] = []

    def _visit(node: object) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "text" and isinstance(value, str):
                    collected.append(value)
                elif key == "text" and isinstance(value, dict):
                    inner = value.get("text")
                    if isinstance(inner, str):
                        collected.append(inner)
                _visit(value)
        elif isinstance(node, list):
            for item in node:
                _visit(item)

    _visit(blocks)
    return collected


class TestBlockKitBuildersClean:
    def test_review_result_blocks_with_findings(self):
        blocks = slack_renderer.build_review_result_blocks(
            pr_number=22,
            summary="리뷰 요약 본문입니다.",
            findings=["발견 1", "발견 2"],
            idempotency_key="abcd-1234",
            job_id=17,
        )
        for text in _walk_user_facing_text(blocks):
            assert find_forbidden_keywords(text) == []

    def test_review_result_blocks_no_findings(self):
        blocks = slack_renderer.build_review_result_blocks(
            pr_number=22,
            summary="리뷰 요약",
            findings=None,
            idempotency_key="key",
            job_id=1,
        )
        for text in _walk_user_facing_text(blocks):
            assert find_forbidden_keywords(text) == []

    def test_merge_confirm_blocks(self):
        blocks = slack_renderer.build_merge_confirm_blocks(
            pr_number=5,
            idempotency_key="key",
            job_id=1,
        )
        for text in _walk_user_facing_text(blocks):
            assert find_forbidden_keywords(text) == []

    def test_review_result_with_dirty_summary_replaced(self):
        # summary 에 도메인 키워드가 들어오면 fallback 으로 치환된다.
        blocks = slack_renderer.build_review_result_blocks(
            pr_number=22,
            summary="dirty signal text",
            findings=None,
            idempotency_key="key",
            job_id=1,
        )
        joined = json.dumps(blocks, ensure_ascii=False)
        # 원본 단어 "signal" 이 발사 텍스트에 새지 않는다.
        assert find_forbidden_keywords(joined) == []


class TestActionValueRoundtrip:
    def test_build_and_parse(self):
        v = slack_renderer.build_action_value("abcd-1234", 42)
        parsed = slack_renderer.parse_action_value(v)
        assert parsed == ("abcd-1234", 42)

    def test_parse_invalid(self):
        assert slack_renderer.parse_action_value(None) is None
        assert slack_renderer.parse_action_value("") is None
        assert slack_renderer.parse_action_value("no-colon") is None
        assert slack_renderer.parse_action_value("abc:notanint") is None


# ---------------------------------------------------------------------------
# 4) PRD / 소스 산출물 정적 검사
# ---------------------------------------------------------------------------


# PRD 본문은 컴플라이언스 정책 자체를 다루는 문맥에서 키워드를 인용해야 한다.
# 본문 내 백틱 코드(`...`) / 코드펜스(``` ... ```) 안에 등장하는 토큰은 정책
# 식별자 인용으로 보고 검사에서 제외한다. 이는 코디네이터 PRD 와 같은 정책.
_BACKTICK_INLINE = re.compile(r"`[^`\n]+`")
_CODE_FENCE = re.compile(r"```.*?```", re.DOTALL)


def _strip_code_blocks(markdown: str) -> str:
    stripped = _CODE_FENCE.sub("", markdown)
    stripped = _BACKTICK_INLINE.sub("", stripped)
    return stripped


def test_prd_body_outside_code_is_clean():
    """PRD 산문(코드 블록·백틱 인용 제외) 에 도메인 키워드가 없는지 (AC-16)."""
    text = PRD_PATH.read_text(encoding="utf-8")
    body = _strip_code_blocks(text)
    matched = find_forbidden_keywords(body)
    assert matched == [], (
        f"PRD 본문에 도메인 키워드가 노출되어 있습니다: {matched}"
    )


def _iter_dev_relay_source_files() -> list[Path]:
    return [
        p for p in DEV_RELAY_DIR.rglob("*.py")
        if p.is_file() and "__pycache__" not in p.parts
    ]


@pytest.mark.parametrize("path", _iter_dev_relay_source_files(), ids=lambda p: p.name)
def test_dev_relay_source_clean(path: Path):
    """dev_relay 소스 파일 전체가 도메인 키워드를 포함하지 않는지 (AC-16)."""
    text = path.read_text(encoding="utf-8")
    matched = find_forbidden_keywords(text)
    assert matched == [], (
        f"{path.relative_to(REPO_ROOT)} 에 도메인 키워드가 포함되어 있습니다: {matched}"
    )
