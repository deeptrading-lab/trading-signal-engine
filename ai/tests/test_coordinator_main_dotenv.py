"""코디네이터 진입점 `.env` 자동 로딩 테스트.

PRD: docs/prd/coordinator-dotenv-autoload.md

- AC-A1: `.env` 만 있고 셸 환경변수가 없을 때 자동 로딩된다.
- AC-O1: 셸 환경변수가 export 되어 있으면 그 값이 우선이고 `.env` 가 덮어쓰지 않는다.
- AC-F1: `.env` 부재 + 셸 환경변수 부재 시 기존 `ConfigError` fail-fast 가 그대로 동작한다.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from ai.coordinator import main as coordinator_main
from ai.coordinator.config import ConfigError, load_config


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------

_TOKEN_ENV_KEYS = (
    "SLACK_BOT_TOKEN",
    "SLACK_APP_TOKEN",
    "SLACK_ALLOWED_USER_IDS",
    "LOG_LEVEL",
)


@pytest.fixture
def clean_env(monkeypatch):
    """테스트 격리 — 기존 셸에 export 된 토큰류를 모두 제거한 환경을 보장."""
    for key in _TOKEN_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    return monkeypatch


def _write_env(dir_path: Path, lines: dict[str, str]) -> Path:
    env_file = dir_path / ".env"
    env_file.write_text("\n".join(f"{k}={v}" for k, v in lines.items()) + "\n")
    return env_file


# ---------------------------------------------------------------------------
# AC-A1 — `.env` 자동 로딩
# ---------------------------------------------------------------------------


class TestDotenvAutoload:
    def test_loads_env_from_cwd(self, tmp_path, clean_env):
        """프로젝트 루트(cwd)의 `.env` 가 자동 로딩되어 환경변수에 적용된다."""
        _write_env(
            tmp_path,
            {
                "SLACK_BOT_TOKEN": "xoxb-FROM-DOTENV",
                "SLACK_APP_TOKEN": "xapp-FROM-DOTENV",
            },
        )
        clean_env.chdir(tmp_path)

        coordinator_main._autoload_dotenv()

        assert os.environ.get("SLACK_BOT_TOKEN") == "xoxb-FROM-DOTENV"
        assert os.environ.get("SLACK_APP_TOKEN") == "xapp-FROM-DOTENV"

        # 후속 `load_config` 가 정상 동작하는지(AC-A1: 기동 직전까지 진행).
        cfg = load_config()
        assert cfg.bot_token == "xoxb-FROM-DOTENV"
        assert cfg.app_token == "xapp-FROM-DOTENV"

    def test_loads_env_from_subdirectory(self, tmp_path, clean_env):
        """하위 디렉토리에서 실행해도 상위 `.env` 를 찾아 로딩한다(`find_dotenv` 동작)."""
        _write_env(
            tmp_path,
            {
                "SLACK_BOT_TOKEN": "xoxb-PARENT-DIR",
                "SLACK_APP_TOKEN": "xapp-PARENT-DIR",
            },
        )
        sub = tmp_path / "nested" / "deep"
        sub.mkdir(parents=True)
        clean_env.chdir(sub)

        coordinator_main._autoload_dotenv()

        assert os.environ.get("SLACK_BOT_TOKEN") == "xoxb-PARENT-DIR"
        assert os.environ.get("SLACK_APP_TOKEN") == "xapp-PARENT-DIR"


# ---------------------------------------------------------------------------
# AC-O1 — 셸 export 우선
# ---------------------------------------------------------------------------


class TestShellOverridesDotenv:
    def test_shell_value_wins_over_dotenv(self, tmp_path, clean_env):
        """셸에 export 된 값이 있으면 `.env` 가 그 값을 덮어쓰지 않는다."""
        _write_env(
            tmp_path,
            {
                "SLACK_BOT_TOKEN": "xoxb-FROM-DOTENV",
                "SLACK_APP_TOKEN": "xapp-FROM-DOTENV",
            },
        )
        clean_env.chdir(tmp_path)

        # 셸 export 모사 — `.env` 와 다른 값.
        clean_env.setenv("SLACK_BOT_TOKEN", "xoxb-FROM-SHELL")
        clean_env.setenv("SLACK_APP_TOKEN", "xapp-FROM-SHELL")

        coordinator_main._autoload_dotenv()

        # 셸 값이 살아 있어야 한다(override=False).
        assert os.environ["SLACK_BOT_TOKEN"] == "xoxb-FROM-SHELL"
        assert os.environ["SLACK_APP_TOKEN"] == "xapp-FROM-SHELL"

        cfg = load_config()
        assert cfg.bot_token == "xoxb-FROM-SHELL"
        assert cfg.app_token == "xapp-FROM-SHELL"

    def test_partial_shell_export_merges_with_dotenv(self, tmp_path, clean_env):
        """셸에 일부만 export 되어 있으면 나머지는 `.env` 값으로 채워진다."""
        _write_env(
            tmp_path,
            {
                "SLACK_BOT_TOKEN": "xoxb-FROM-DOTENV",
                "SLACK_APP_TOKEN": "xapp-FROM-DOTENV",
            },
        )
        clean_env.chdir(tmp_path)
        clean_env.setenv("SLACK_BOT_TOKEN", "xoxb-FROM-SHELL")  # APP_TOKEN 은 미설정.

        coordinator_main._autoload_dotenv()

        assert os.environ["SLACK_BOT_TOKEN"] == "xoxb-FROM-SHELL"
        assert os.environ["SLACK_APP_TOKEN"] == "xapp-FROM-DOTENV"


# ---------------------------------------------------------------------------
# AC-F1 — `.env` 부재 시 기존 fail-fast 회귀 무결
# ---------------------------------------------------------------------------


class TestDotenvAbsentFailsFast:
    def test_autoload_is_silent_when_no_dotenv(self, tmp_path, clean_env):
        """`.env` 가 없는 디렉토리에서 호출해도 예외를 던지지 않는다."""
        empty = tmp_path / "empty"
        empty.mkdir()
        clean_env.chdir(empty)

        # 예외 없이 통과해야 한다.
        coordinator_main._autoload_dotenv()

        # 환경변수도 새로 만들어지지 않아야 한다.
        assert os.environ.get("SLACK_BOT_TOKEN") is None
        assert os.environ.get("SLACK_APP_TOKEN") is None

    def test_run_returns_nonzero_when_dotenv_absent_and_shell_empty(
        self, tmp_path, clean_env, capsys
    ):
        """`.env` 부재 + 셸 환경변수 부재 시 `run()` 이 non-zero 종료 코드를 반환한다."""
        empty = tmp_path / "empty"
        empty.mkdir()
        clean_env.chdir(empty)

        exit_code = coordinator_main.run()

        assert exit_code != 0
        captured = capsys.readouterr()
        # 한 줄 fail-fast 포맷이 유지된다(트레이싱백 미노출).
        assert "[코디네이터] 시작 실패" in captured.err
        assert "SLACK_BOT_TOKEN" in captured.err
        # 평문 토큰이 노출될 일은 없지만, 기존 마스킹 원칙도 회귀 무결.
        assert "Traceback" not in captured.err

    def test_load_config_raises_when_environment_empty(self, clean_env):
        """기존 `ConfigError` fail-fast 가 그대로 동작함을 명시 회귀."""
        with pytest.raises(ConfigError):
            load_config()
