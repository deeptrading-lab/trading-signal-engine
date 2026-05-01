"""코디네이터 dispatcher 통합 테스트.

PRD: docs/prd/coordinator-code-chore.md (#6)

`ai.coordinator.main._dispatch_message` 가 `handle_message_im` 클로저에서
모듈 함수로 추출됨에 따라, mock `say` 기반으로 라우팅 분기 5종을 직접 검증한다.

시나리오
- 정상: IM + ping → safe_say 경유 pong 응답
- 봇 자기 메시지: bot_id 채워짐 → 무응답
- 비-IM 채널: channel_type=channel → 무응답
- 비처리 subtype: subtype=message_changed → 무응답 + INFO 로그
- 비허용 발신자: allowed_user_ids 외 user → 무응답 + INFO 로그
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

from ai.coordinator.config import CoordinatorConfig
from ai.coordinator.main import _dispatch_message


# ---------------------------------------------------------------------------
# fixture
# ---------------------------------------------------------------------------


SELF_USER_ID = "UBOTSELF"
ALLOWED_USER_ID = "U0AE7A54NHL"


@pytest.fixture
def config() -> CoordinatorConfig:
    return CoordinatorConfig(
        bot_token="xoxb-test",
        app_token="xapp-test",
        allowed_user_ids=frozenset({ALLOWED_USER_ID}),
        log_level="INFO",
    )


@pytest.fixture
def say() -> MagicMock:
    return MagicMock(name="say")


@pytest.fixture
def safe_say_fn() -> MagicMock:
    return MagicMock(name="safe_say_fn")


@pytest.fixture
def logger() -> MagicMock:
    return MagicMock(spec=logging.Logger)


# ---------------------------------------------------------------------------
# 1) 정상 ping → safe_say 호출 + pong 응답
# ---------------------------------------------------------------------------


class TestNormalPing:
    def test_im_ping_invokes_safe_say_with_pong(
        self, say, safe_say_fn, logger, config
    ):
        event = {
            "type": "message",
            "channel_type": "im",
            "user": ALLOWED_USER_ID,
            "text": "ping",
        }

        _dispatch_message(
            event,
            say=say,
            logger=logger,
            config=config,
            self_user_id=SELF_USER_ID,
            safe_say_fn=safe_say_fn,
        )

        assert safe_say_fn.call_count == 1
        args, kwargs = safe_say_fn.call_args
        # 시그니처: safe_say(say, text, logger, *, context=...)
        assert args[0] is say
        assert args[1] == "pong"
        assert args[2] is logger
        assert kwargs.get("context") == "route_command"
        say.assert_not_called()  # 가드 wrapper 만 거치고 직접 say 는 호출되지 않는다.


# ---------------------------------------------------------------------------
# 2) 자기 메시지 → 응답 없음
# ---------------------------------------------------------------------------


class TestSelfMessageIgnored:
    def test_bot_id_present_skips_dispatch(
        self, say, safe_say_fn, logger, config
    ):
        event = {
            "type": "message",
            "channel_type": "im",
            "user": SELF_USER_ID,
            "bot_id": "B12345",  # 봇 자기 메시지 표지.
            "text": "ping",
        }

        _dispatch_message(
            event,
            say=say,
            logger=logger,
            config=config,
            self_user_id=SELF_USER_ID,
            safe_say_fn=safe_say_fn,
        )

        safe_say_fn.assert_not_called()
        say.assert_not_called()


# ---------------------------------------------------------------------------
# 3) 비-IM 채널 → 응답 없음
# ---------------------------------------------------------------------------


class TestNonImChannelIgnored:
    def test_channel_type_channel_skips_dispatch(
        self, say, safe_say_fn, logger, config
    ):
        event = {
            "type": "message",
            "channel_type": "channel",
            "user": ALLOWED_USER_ID,
            "text": "ping",
        }

        _dispatch_message(
            event,
            say=say,
            logger=logger,
            config=config,
            self_user_id=SELF_USER_ID,
            safe_say_fn=safe_say_fn,
        )

        safe_say_fn.assert_not_called()
        say.assert_not_called()


# ---------------------------------------------------------------------------
# 4) 비처리 subtype → 응답 없음 + INFO 로그
# ---------------------------------------------------------------------------


class TestUnhandleableSubtypeIgnored:
    def test_message_changed_skips_dispatch_and_logs_info(
        self, say, safe_say_fn, logger, config
    ):
        event = {
            "type": "message",
            "channel_type": "im",
            "subtype": "message_changed",
            "message": {"user": ALLOWED_USER_ID, "text": "ping"},
        }

        _dispatch_message(
            event,
            say=say,
            logger=logger,
            config=config,
            self_user_id=SELF_USER_ID,
            safe_say_fn=safe_say_fn,
        )

        safe_say_fn.assert_not_called()
        say.assert_not_called()
        # INFO 로그 1회.
        assert logger.info.called
        first_format = logger.info.call_args_list[0].args[0]
        assert "처리 대상이 아닌" in first_format


# ---------------------------------------------------------------------------
# 5) 비허용 발신자 → 응답 없음 + INFO 로그
# ---------------------------------------------------------------------------


class TestDisallowedSenderIgnored:
    def test_unknown_user_skips_dispatch_and_logs_info(
        self, say, safe_say_fn, logger, config
    ):
        event = {
            "type": "message",
            "channel_type": "im",
            "user": "UUNKNOWN1",  # 화이트리스트 외.
            "text": "ping",
        }

        _dispatch_message(
            event,
            say=say,
            logger=logger,
            config=config,
            self_user_id=SELF_USER_ID,
            safe_say_fn=safe_say_fn,
        )

        safe_say_fn.assert_not_called()
        say.assert_not_called()
        assert logger.info.called
        first_format = logger.info.call_args_list[0].args[0]
        assert "허용되지 않은 발신자" in first_format
