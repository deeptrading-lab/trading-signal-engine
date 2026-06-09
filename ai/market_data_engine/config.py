from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    supabase_url: str
    supabase_secret_key: str
    engine_write_token: str
    kis_app_key: str = ""
    kis_app_secret: str = ""
    kis_environment: str = "prod"
    kis_stream_enabled: bool = False
    kis_symbols: tuple[str, ...] = ()
    host: str = "0.0.0.0"
    port: int = 8000
    frontend_origin: str = "http://localhost:3000"
    kis_rest_url: str = ""
    kis_ws_url: str = ""

    @classmethod
    def from_env(cls) -> "Settings":
        environment = os.getenv("KIS_ENVIRONMENT", "prod").strip().lower()
        if environment not in {"prod", "vps"}:
            raise ValueError("KIS_ENVIRONMENT must be prod or vps")
        return cls(
            supabase_url=os.getenv("SUPABASE_URL", "").strip(),
            supabase_secret_key=(
                os.getenv("SUPABASE_SECRET_KEY", "").strip()
                or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
            ),
            engine_write_token=os.getenv("ENGINE_WRITE_TOKEN", "").strip(),
            kis_app_key=os.getenv("KIS_APP_KEY", "").strip(),
            kis_app_secret=os.getenv("KIS_APP_SECRET", "").strip(),
            kis_environment=environment,
            kis_stream_enabled=_bool_env("KIS_STREAM_ENABLED", False),
            kis_symbols=tuple(
                value.strip()
                for value in os.getenv("KIS_SYMBOLS", "").split(",")
                if value.strip()
            ),
            host=os.getenv("HOST", "0.0.0.0"),
            port=int(os.getenv("PORT", "8000")),
            frontend_origin=os.getenv("FRONTEND_ORIGIN", "http://localhost:3000"),
            kis_rest_url=os.getenv("KIS_REST_URL", "").strip(),
            kis_ws_url=os.getenv("KIS_WS_URL", "").strip(),
        )

    def validate(self) -> None:
        if not self.supabase_url:
            raise ValueError("SUPABASE_URL is required")
        if not self.supabase_secret_key:
            raise ValueError("SUPABASE_SECRET_KEY is required")
        if self.supabase_secret_key.startswith("sb_publishable_"):
            raise ValueError("Supabase publishable key cannot be used by the engine")
        if not self.engine_write_token:
            raise ValueError("ENGINE_WRITE_TOKEN is required")
        if self.kis_stream_enabled and (not self.kis_app_key or not self.kis_app_secret):
            raise ValueError("KIS_APP_KEY and KIS_APP_SECRET are required for streaming")


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}
