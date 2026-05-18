"""`_post_blocks_to_thread` 의 blocks 정적 가드 단위 테스트.

PR #43 reviewer P2-3 후속. 호출 측 (`build_review_result_blocks`) 이
`guard_text` 를 이미 통과시키더라도, 미래에 다른 호출자가 `blocks` 를 직접
조립해 넘기는 회귀를 막기 위한 발사 직전 한 번 더의 정적 검사.

본 파일은 fixture 로 정책 키워드를 의도적으로 포함한다 (코디네이터의
`test_coordinator_compliance.py` / `test_compliance.py` 와 동일 예외).
"""

from __future__ import annotations

import logging
from typing import Any

import pytest

from ai.coordinator._compliance import find_forbidden_keywords
from ai.dev_relay.main import (
    _collect_block_user_facing_text,
    _post_blocks_to_thread,
)
from ai.dev_relay.slack_renderer import FALLBACK_RESPONSE


class _FakeClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def chat_postMessage(self, **kwargs: Any) -> None:  # noqa: N802
        self.calls.append(kwargs)


class _FakeApp:
    def __init__(self) -> None:
        self.client = _FakeClient()


def _logger() -> logging.Logger:
    # caplog 호환 — 모듈 logger 가 아닌 일반 root 자식 사용은 의도적으로 회피.
    return logging.getLogger("ai.dev_relay.test_post_blocks_guard")


class TestCollectBlockUserFacingText:
    """walker 가 사용자 노출 텍스트만 수집하는지 (중복은 무관 — 발사 차단 판정에 영향 0)."""

    def test_collects_section_text(self):
        blocks = [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "안녕하세요. 본문입니다."},
            }
        ]
        collected = _collect_block_user_facing_text(blocks)
        assert "안녕하세요. 본문입니다." in collected

    def test_collects_button_plain_text(self):
        blocks = [
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "승인"},
                    }
                ],
            }
        ]
        assert "승인" in _collect_block_user_facing_text(blocks)

    def test_ignores_action_id_and_value(self):
        blocks = [
            {
                "type": "actions",
                "block_id": "review_actions_1",
                "elements": [
                    {
                        "type": "button",
                        "action_id": "approve_merge",
                        "value": "pr=22;key=abcd;job=1",
                        "text": {"type": "plain_text", "text": "승인"},
                    }
                ],
            }
        ]
        # action_id / block_id / value 는 사용자 노출 텍스트가 아니므로 수집되지 않는다.
        collected = _collect_block_user_facing_text(blocks)
        # `approve_merge`, `review_actions_1`, `pr=22;key=abcd;job=1` 가 노출되지 않음.
        assert "approve_merge" not in collected
        assert "review_actions_1" not in collected
        assert "pr=22;key=abcd;job=1" not in collected
        assert "승인" in collected

    def test_text_object_not_double_collected(self):
        """PR #51 reviewer P2 #2: `key == "text"` 분기에서 inner 만 한 번 수집.

        text 객체 ({type, text}) 가 들어왔을 때 inner 텍스트는 한 번만 수집된다.
        (중복 수집은 발사 차단 판정에 영향 0 이지만 walker 의도 명확화 차원.)
        """
        blocks = [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "한 번만 수집되어야 합니다"},
            }
        ]
        collected = _collect_block_user_facing_text(blocks)
        assert collected.count("한 번만 수집되어야 합니다") == 1


class TestCollectBlockNonTextKeys:
    """PR #51 reviewer P2 #3: 비-text 키 누락 위험 보강 회귀.

    현재 호출 경로에는 image / input 블록이 없지만, 미래 도입 시 누설을 막기
    위해 walker 가 다음 키도 수집해야 한다.
    """

    def test_image_alt_text_collected(self):
        blocks = [
            {
                "type": "image",
                "image_url": "https://example.com/x.png",
                "alt_text": "차트 이미지 설명",
            }
        ]
        collected = _collect_block_user_facing_text(blocks)
        assert "차트 이미지 설명" in collected

    def test_input_placeholder_collected(self):
        blocks = [
            {
                "type": "input",
                "label": {"type": "plain_text", "text": "라벨 텍스트"},
                "element": {
                    "type": "plain_text_input",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "여기에 입력하세요",
                    },
                },
            }
        ]
        collected = _collect_block_user_facing_text(blocks)
        assert "라벨 텍스트" in collected
        assert "여기에 입력하세요" in collected

    def test_actions_select_placeholder_collected(self):
        blocks = [
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "static_select",
                        "placeholder": {
                            "type": "plain_text",
                            "text": "옵션을 선택하세요",
                        },
                    }
                ],
            }
        ]
        assert "옵션을 선택하세요" in _collect_block_user_facing_text(blocks)

    def test_image_title_collected(self):
        blocks = [
            {
                "type": "image",
                "image_url": "https://example.com/x.png",
                "alt_text": "ok",
                "title": {"type": "plain_text", "text": "이미지 캡션"},
            }
        ]
        assert "이미지 캡션" in _collect_block_user_facing_text(blocks)

    def test_dirty_alt_text_blocks_post(self):
        """image.alt_text 에 도메인 키워드가 있으면 발사 차단된다 (회귀 안전망)."""
        app = _FakeApp()
        dirty_blocks = [
            {
                "type": "image",
                "image_url": "https://example.com/x.png",
                "alt_text": "leaked signal token",
            }
        ]
        _post_blocks_to_thread(
            app=app,
            channel="C1",
            thread_ts="123.456",
            blocks=dirty_blocks,
            text="알림",
            logger=_logger(),
        )
        assert len(app.client.calls) == 1
        # blocks 가 발사되지 않고 text-only fallback 으로 전환.
        assert "blocks" not in app.client.calls[0]
        assert app.client.calls[0]["text"] == FALLBACK_RESPONSE


class TestPostBlocksGuardClean:
    """정상 케이스 회귀: 가드 통과 blocks 는 그대로 발사."""

    def test_clean_blocks_posted_with_blocks(self):
        app = _FakeApp()
        blocks = [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "*PR #22 리뷰 결과*\n깔끔합니다."},
            }
        ]
        _post_blocks_to_thread(
            app=app,
            channel="C1",
            thread_ts="123.456",
            blocks=blocks,
            text="PR #22 리뷰 결과",
            logger=_logger(),
        )
        assert len(app.client.calls) == 1
        call = app.client.calls[0]
        assert call["channel"] == "C1"
        assert call["thread_ts"] == "123.456"
        assert call["blocks"] == blocks
        assert call["text"] == "PR #22 리뷰 결과"


class TestPostBlocksGuardViolation:
    """발사 차단 케이스: blocks 내부에 도메인 키워드가 있으면 차단."""

    def test_dirty_blocks_blocked_and_text_fallback(self, caplog):
        app = _FakeApp()
        # 미래의 다른 호출자가 가드 미통과 blocks 를 넘긴다고 가정.
        dirty_blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "leaked signal token inside blocks",
                },
            }
        ]
        with caplog.at_level(logging.ERROR, logger="ai.dev_relay.test_post_blocks_guard"):
            _post_blocks_to_thread(
                app=app,
                channel="C1",
                thread_ts="123.456",
                blocks=dirty_blocks,
                text="알림 본문",
                logger=_logger(),
            )

        assert len(app.client.calls) == 1
        call = app.client.calls[0]
        # blocks 인자 자체가 발사되지 않는다 (text-only fallback).
        assert "blocks" not in call
        # fallback 본문 자체는 가드 통과 — 도메인 키워드 0 hit.
        assert call["text"] == FALLBACK_RESPONSE
        assert find_forbidden_keywords(call["text"]) == []
        # 에러 로그 발사 확인.
        assert any(
            "compliance: blocked thread blocks post" in record.getMessage()
            for record in caplog.records
        )

    def test_dirty_button_label_blocked(self):
        app = _FakeApp()
        dirty_blocks = [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "깔끔한 본문"},
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "action_id": "approve_merge",
                        "text": {"type": "plain_text", "text": "trade approve"},
                    }
                ],
            },
        ]
        _post_blocks_to_thread(
            app=app,
            channel="C1",
            thread_ts="123.456",
            blocks=dirty_blocks,
            text="알림",
            logger=_logger(),
        )
        # 발사된 call 은 fallback 1건만.
        assert len(app.client.calls) == 1
        assert "blocks" not in app.client.calls[0]
        assert app.client.calls[0]["text"] == FALLBACK_RESPONSE

    def test_dirty_text_argument_replaced_blocks_still_clean(self):
        """blocks 는 깔끔하지만 `text` 인자가 더러우면 text 만 fallback 으로 교체."""
        app = _FakeApp()
        clean_blocks = [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "깔끔한 본문"},
            }
        ]
        _post_blocks_to_thread(
            app=app,
            channel="C1",
            thread_ts="123.456",
            blocks=clean_blocks,
            text="dirty market alert",
            logger=_logger(),
        )
        assert len(app.client.calls) == 1
        call = app.client.calls[0]
        # blocks 는 그대로 발사 (가드 통과).
        assert call["blocks"] == clean_blocks
        # text 만 fallback.
        assert call["text"] == FALLBACK_RESPONSE


class TestPostBlocksHandlesSlackException:
    def test_swallows_post_exception(self):
        class _RaisingClient:
            def chat_postMessage(self, **kwargs: Any) -> None:  # noqa: N802
                raise RuntimeError("network")

        class _RaisingApp:
            client = _RaisingClient()

        clean_blocks = [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "깔끔"},
            }
        ]
        # 예외가 호출 측으로 새지 않는다 — warning 로깅 후 정상 반환.
        _post_blocks_to_thread(
            app=_RaisingApp(),
            channel="C1",
            thread_ts="123.456",
            blocks=clean_blocks,
            text="OK",
            logger=_logger(),
        )


# ---------------------------------------------------------------------------
# `validate_approval` 재시작 거절 흐름 통합 점검 — P2-1
# ---------------------------------------------------------------------------


class TestApprovalRestartGuard:
    """PR #43 reviewer P2-1 후속: 데몬 재시작 후 이전 세션 페이로드는 거절."""

    def _ctor_kwargs(self) -> dict[str, Any]:
        return {
            "pr_number_in_payload": 22,
            "idempotency_key_in_payload": "abcd-1234",
            "job_id_in_payload": 7,
            "user_id": "U0AE7A54NHL",
            "allowed_user_ids": frozenset({"U0AE7A54NHL"}),
            "action_id": "approve_merge",
        }

    def test_restart_session_rejected(self):
        from ai.dev_relay.merger import (
            REJECTION_REASON_RESTART_NO_EXPECTED,
            MergeRejection,
            validate_approval,
        )

        kwargs = self._ctor_kwargs() | {
            "expected_idempotency_key": None,
            "expected_job_id": None,
        }
        with pytest.raises(MergeRejection) as exc_info:
            validate_approval(**kwargs)
        assert str(exc_info.value) == REJECTION_REASON_RESTART_NO_EXPECTED

    def test_template_restart_rejected_compliance_clean(self):
        from ai.dev_relay.slack_renderer import TEMPLATE_RESTART_APPROVAL_REJECTED

        assert find_forbidden_keywords(TEMPLATE_RESTART_APPROVAL_REJECTED) == []
