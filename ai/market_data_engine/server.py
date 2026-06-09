from __future__ import annotations

import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated, Any, AsyncIterator
from uuid import uuid4

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .config import Settings
from .kis import KISClient
from .models import (
    CandleSyncRequest,
    ExternalAnalysisCreate,
    ExternalAnalysisUpdate,
    InstrumentCreate,
    InstrumentUpdate,
)
from .repository import MarketDataRepository, RepositoryError, SupabaseRepository
from .stream import MarketStreamService, StreamBroadcaster

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None


def create_app(
    settings: Settings | None = None,
    repository: MarketDataRepository | None = None,
    kis_client: KISClient | None = None,
) -> FastAPI:
    settings = settings or _load_settings()
    settings.validate()
    repository = repository or SupabaseRepository(
        settings.supabase_url, settings.supabase_secret_key
    )
    kis_client = kis_client or KISClient(
        settings.kis_app_key,
        settings.kis_app_secret,
        environment=settings.kis_environment,
        rest_url=settings.kis_rest_url,
        ws_url=settings.kis_ws_url,
    )
    broadcaster = StreamBroadcaster()
    stream: MarketStreamService | None = None

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        nonlocal stream
        if settings.kis_stream_enabled:
            symbols = settings.kis_symbols
            if not symbols:
                rows = await repository.list_rows(
                    "instruments",
                    filters={"enabled": "true"},
                    limit=100,
                    order="symbol.asc",
                )
                symbols = tuple(str(row["symbol"]) for row in rows)
            if symbols:
                stream = MarketStreamService(
                    repository, kis_client, broadcaster, symbols
                )
                app.state.stream = stream
        if stream is not None:
            stream.start()
        yield
        if stream is not None:
            await stream.stop()

    app = FastAPI(title="Trading Signal Market Data Engine", version="2.0.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.settings = settings
    app.state.repository = repository
    app.state.kis_client = kis_client
    app.state.broadcaster = broadcaster
    app.state.stream = None

    async def require_write_token(
        authorization: Annotated[str | None, Header()] = None,
    ) -> None:
        expected = settings.engine_write_token
        actual = authorization.removeprefix("Bearer ").strip() if authorization else ""
        if not actual or not secrets.compare_digest(actual, expected):
            raise HTTPException(status_code=401, detail="unauthorized")

    @app.exception_handler(RepositoryError)
    async def repository_error_handler(_: Any, error: RepositoryError) -> Any:
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=502, content={"detail": str(error)})

    @app.exception_handler(httpx.HTTPError)
    async def provider_http_error_handler(_: Any, error: httpx.HTTPError) -> Any:
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=502, content={"detail": f"KIS request failed: {error}"}
        )

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {
            "ok": True,
            "service": "market-data-engine",
            "database": "supabase",
            "stream": (
                stream.health()
                if stream
                else {
                    "enabled": settings.kis_stream_enabled,
                    "connected": False,
                    "symbols": [],
                }
            ),
        }

    @app.get("/api/v1/instruments")
    async def list_instruments(enabled: bool | None = None) -> list[dict[str, Any]]:
        filters = {"enabled": str(enabled).lower()} if enabled is not None else None
        return await repository.list_rows(
            "instruments", filters=filters, order="symbol.asc"
        )

    @app.post("/api/v1/instruments", status_code=201)
    async def create_instrument(
        payload: InstrumentCreate, _auth: None = Depends(require_write_token)
    ) -> dict[str, Any]:
        return await repository.create_row("instruments", payload.model_dump())

    @app.patch("/api/v1/instruments/{symbol}")
    async def update_instrument(
        symbol: str,
        payload: InstrumentUpdate,
        _auth: None = Depends(require_write_token),
    ) -> dict[str, Any]:
        row = await repository.update_row(
            "instruments", "symbol", symbol.upper(), payload.model_dump(exclude_none=True)
        )
        if not row:
            raise HTTPException(status_code=404, detail="instrument not found")
        return row

    @app.delete("/api/v1/instruments/{symbol}", status_code=204)
    async def delete_instrument(
        symbol: str, _auth: None = Depends(require_write_token)
    ) -> None:
        if not await repository.delete_row("instruments", "symbol", symbol.upper()):
            raise HTTPException(status_code=404, detail="instrument not found")

    @app.get("/api/v1/analyses")
    async def list_analyses(
        symbol: str | None = None,
        analysis_type: str | None = None,
        limit: int = Query(default=100, ge=1, le=1000),
    ) -> list[dict[str, Any]]:
        filters = {
            key: value
            for key, value in {"symbol": symbol, "analysis_type": analysis_type}.items()
            if value
        }
        return await repository.list_rows(
            "external_analyses",
            filters=filters,
            limit=limit,
            order="observed_at.desc",
        )

    @app.get("/api/v1/analyses/{analysis_id}")
    async def get_analysis(analysis_id: str) -> dict[str, Any]:
        row = await repository.get_row("external_analyses", "id", analysis_id)
        if not row:
            raise HTTPException(status_code=404, detail="analysis not found")
        return row

    @app.post("/api/v1/analyses", status_code=201)
    async def create_analysis(
        payload: ExternalAnalysisCreate,
        _auth: None = Depends(require_write_token),
    ) -> dict[str, Any]:
        row = payload.model_dump(mode="json")
        row["id"] = str(uuid4())
        return await repository.create_row("external_analyses", row)

    @app.patch("/api/v1/analyses/{analysis_id}")
    async def update_analysis(
        analysis_id: str,
        payload: ExternalAnalysisUpdate,
        _auth: None = Depends(require_write_token),
    ) -> dict[str, Any]:
        changes = payload.model_dump(exclude_none=True, mode="json")
        changes["updated_at"] = datetime.now(timezone.utc).isoformat()
        row = await repository.update_row(
            "external_analyses", "id", analysis_id, changes
        )
        if not row:
            raise HTTPException(status_code=404, detail="analysis not found")
        return row

    @app.delete("/api/v1/analyses/{analysis_id}", status_code=204)
    async def delete_analysis(
        analysis_id: str, _auth: None = Depends(require_write_token)
    ) -> None:
        if not await repository.delete_row("external_analyses", "id", analysis_id):
            raise HTTPException(status_code=404, detail="analysis not found")

    @app.get("/api/v1/ticks")
    async def list_ticks(
        symbol: str,
        limit: int = Query(default=100, ge=1, le=1000),
    ) -> list[dict[str, Any]]:
        return await repository.list_rows(
            "market_ticks",
            filters={"symbol": symbol.upper()},
            limit=limit,
            order="occurred_at.desc",
        )

    @app.get("/api/v1/candles")
    async def list_candles(
        symbol: str,
        interval: str,
        limit: int = Query(default=100, ge=1, le=1000),
    ) -> list[dict[str, Any]]:
        if interval not in {"1m", "1d", "1w", "1mo"}:
            raise HTTPException(status_code=400, detail="unsupported interval")
        return await repository.list_rows(
            "market_candles",
            filters={"symbol": symbol.upper(), "interval": interval},
            limit=limit,
            order="opened_at.desc",
        )

    @app.post("/api/v1/candles/sync")
    async def sync_candles(
        payload: CandleSyncRequest, _auth: None = Depends(require_write_token)
    ) -> dict[str, Any]:
        candles = await kis_client.fetch_candles(
            payload.symbol.upper(),
            payload.interval,
            start=payload.start,
            end=payload.end,
            hour=payload.hour,
        )
        await repository.upsert_candles(candles)
        return {"symbol": payload.symbol.upper(), "interval": payload.interval, "count": len(candles)}

    @app.websocket("/ws/market")
    async def market_websocket(websocket: WebSocket) -> None:
        token = websocket.query_params.get("token", "")
        if not token or not secrets.compare_digest(token, settings.engine_write_token):
            await websocket.close(code=4401)
            return
        await broadcaster.connect(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            broadcaster.disconnect(websocket)

    return app


def _load_settings() -> Settings:
    if load_dotenv is not None:
        load_dotenv(".env", override=False)
        load_dotenv(".env.local", override=True)
    return Settings.from_env()


def main() -> None:
    import uvicorn

    settings = _load_settings()
    uvicorn.run(
        create_app(settings),
        host=settings.host,
        port=settings.port,
    )


if __name__ == "__main__":
    main()
