"""
코디네이터 데몬 엔트리포인트.

PRD: docs/prd/slack-coordinator-inbound.md

실행:
    python -m ai.coordinator.main

동작:
- 환경변수 검증(fail-fast) → Socket Mode 클라이언트 시작.
- `message.im` 이벤트만 처리. 화이트리스트 외 발신자·봇 자기 메시지는 무시.
- SIGINT/SIGTERM 수신 시 graceful shutdown.
"""

from __future__ import annotations

import logging
import signal
import sys
from typing import Any

from ai.coordinator.auth import (
    is_allowed_sender,
    is_handleable_message_subtype,
    is_self_message,
    mask_user_id,
)
from ai.coordinator.config import ConfigError, CoordinatorConfig, load_config
from ai.coordinator.handlers import route_command

_LOGGER_NAME = "ai.coordinator"


def _setup_logging(level: str) -> logging.Logger:
    """루트 핸들러를 설정하고 모듈 로거 반환. 토큰은 절대 로그에 흐르지 않는다."""
    numeric_level = getattr(logging, level, logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    return logging.getLogger(_LOGGER_NAME)


def _resolve_self_user_id(app: Any, logger: logging.Logger) -> str | None:
    """`auth.test` 로 봇 자신의 user id 획득. 실패해도 데몬은 계속 동작한다."""
    try:
        response = app.client.auth_test()
        return response.get("user_id")
    except Exception as exc:  # noqa: BLE001 — 외부 호출 실패는 INFO 로그만.
        logger.warning("자기 식별자 조회 실패: %s", type(exc).__name__)
        return None


def build_app(config: CoordinatorConfig, logger: logging.Logger) -> Any:
    """
    slack-bolt App 을 구성한다. 의존성 분리를 위해 별도 함수로 분리해 두면
    엔트리포인트 단위 테스트를 작성하기 쉽다(본 PR 범위 외).

    NOTE: slack-bolt 는 런타임 의존성이다. 단위 테스트(handlers/auth/config)
    에서는 본 함수를 import 하지 않으므로 import 비용이 새지 않는다.
    """
    from slack_bolt import App  # 지역 import — 런타임에만 필요.

    app = App(token=config.bot_token, logger=logger)
    self_user_id = _resolve_self_user_id(app, logger)

    @app.event("message")
    def handle_message_im(event: dict, say: Any, logger: logging.Logger = logger) -> None:
        # AC-9: 봇 자기 메시지는 즉시 반환.
        if is_self_message(event, self_user_id):
            return

        # MVP 는 DM(IM)만 처리. 그 외 채널 타입은 무시.
        if event.get("channel_type") != "im":
            return

        # PRD slack-message-subtype-guard: 편집·삭제·시스템 메시지 등은 조용히 무시.
        if not is_handleable_message_subtype(event):
            logger.info(
                "처리 대상이 아닌 메시지 이벤트를 무시했습니다 "
                "(subtype=%s, sender=%s, type=%s)",
                event.get("subtype"),
                mask_user_id(event.get("user")),
                event.get("type"),
            )
            return

        sender = event.get("user")

        # AC-5: 화이트리스트 외 발신자는 무시 + INFO 로그.
        if not is_allowed_sender(sender, config.allowed_user_ids):
            logger.info(
                "허용되지 않은 발신자 메시지를 무시했습니다 (sender=%s, type=%s)",
                mask_user_id(sender),
                event.get("type"),
            )
            return

        text = event.get("text") or ""
        reply = route_command(text)
        say(reply)

    # `app_mention` 이벤트가 들어와도 무시(스코프 회수 전 안전장치).
    @app.event("app_mention")
    def ignore_mentions(event: dict, logger: logging.Logger = logger) -> None:  # noqa: ARG001
        return

    return app


def _install_signal_handlers(logger: logging.Logger) -> None:
    """SIGINT/SIGTERM 수신 시 KeyboardInterrupt 로 변환해 메인 스레드 wait 를 깨운다 (AC-6).

    slack-bolt SocketModeHandler.start() 은 메인 스레드에서 블록하며 KeyboardInterrupt
    를 받을 때 정상 종료한다. close()/sys.exit() 를 시그널 핸들러 안에서 직접 호출하면
    내부 wait 가 깨어나지 않아 종료가 멈추는 사례가 있어 raise 방식으로 통일한다.
    """

    def _shutdown(signum: int, _frame: Any) -> None:
        logger.info("종료 시그널 수신(%s) — 코디네이터를 정리 중입니다.", signum)
        # close() 도중 추가 시그널이 들어와 재진입하면 lock 위에서 KeyboardInterrupt 가
        # 다시 raise 되어 traceback 이 노출된다. 첫 신호 이후엔 기본 핸들러로 되돌려
        # 다음 Ctrl+C 가 와도 표준 종료 흐름을 따르게 한다.
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        try:
            signal.signal(signal.SIGTERM, signal.SIG_DFL)
        except (ValueError, AttributeError):
            pass
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, _shutdown)
    try:
        signal.signal(signal.SIGTERM, _shutdown)
    except (ValueError, AttributeError):
        # Windows 등 SIGTERM 미지원 환경에서는 무시.
        pass


def run() -> int:
    """데몬 메인 루프. 종료 코드(0=정상)를 반환한다."""
    try:
        config = load_config()
    except ConfigError as exc:
        # AC-7: 한 줄 메시지 + 비정상 exit. 토큰은 노출되지 않는다.
        print(f"[코디네이터] 시작 실패: {exc}", file=sys.stderr)
        return 2

    logger = _setup_logging(config.log_level)
    logger.info("코디네이터를 시작합니다. %s", config.with_masked_repr())

    app = build_app(config, logger)

    # SocketModeHandler 는 slack-bolt 에 포함되어 있다.
    from slack_bolt.adapter.socket_mode import SocketModeHandler

    handler = SocketModeHandler(app=app, app_token=config.app_token)
    _install_signal_handlers(logger)

    try:
        logger.info("Socket Mode 연결을 시도합니다.")
        handler.start()
    except KeyboardInterrupt:
        logger.info("키보드 인터럽트로 종료합니다.")
    except Exception as exc:  # noqa: BLE001 — 최상위 트랩.
        logger.error("예상치 못한 종료: %s", type(exc).__name__)
        return 1
    finally:
        try:
            handler.close()
        except Exception:  # noqa: BLE001
            pass
        logger.info("코디네이터를 정리했습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
