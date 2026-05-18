from __future__ import annotations

import os
import time
from collections import defaultdict, deque
from dataclasses import asdict, is_dataclass
from hmac import compare_digest
from typing import Any

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .models import AnalysisInput
from .whitelist import WHITELIST, WhitelistError
from .workbench import analyze_workbench


class AnalyzeRequest(BaseModel):
    ticker: str
    capital_amount: float = Field(gt=0)
    target_return_pct: float = Field(ge=0)
    target_period_days: int = Field(gt=0)
    max_loss_pct: float = Field(default=2.0, gt=0, le=5)
    offline: bool = False


_RATE_LIMIT_BUCKETS: dict[str, deque[float]] = defaultdict(deque)


def _cors_origins() -> list[str]:
    configured = os.getenv("CORS_ORIGINS")
    if configured:
        return [origin.strip() for origin in configured.split(",") if origin.strip()]
    return ["http://localhost:3000", "http://127.0.0.1:3000"]


def _configured_api_keys() -> list[str]:
    configured = os.getenv("WORKBENCH_API_KEYS", "")
    return [key.strip() for key in configured.split(",") if key.strip()]


def _allow_unauthenticated_workbench() -> bool:
    return os.getenv("ALLOW_UNAUTHENTICATED_WORKBENCH", "0") == "1"


def _rate_limit_window_seconds() -> int:
    return max(1, int(os.getenv("WORKBENCH_RATE_LIMIT_WINDOW_SECONDS", "60")))


def _rate_limit_requests() -> int:
    return max(1, int(os.getenv("WORKBENCH_RATE_LIMIT_REQUESTS", "30")))


def _client_identifier(request: Request, api_key: str | None) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    client_ip = forwarded_for.split(",", 1)[0].strip()
    if not client_ip and request.client is not None:
        client_ip = request.client.host
    return f"{api_key or 'anonymous'}:{client_ip or 'unknown'}"


def _extract_bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token.strip()


def _authenticate_workbench(
    request: Request,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> None:
    api_keys = _configured_api_keys()
    supplied_key = x_api_key or _extract_bearer(authorization)
    if not api_keys:
        if _allow_unauthenticated_workbench():
            _enforce_rate_limit(_client_identifier(request, supplied_key))
            return
        raise HTTPException(status_code=503, detail="Workbench API authentication is not configured")
    if supplied_key is None or not any(compare_digest(supplied_key, key) for key in api_keys):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    _enforce_rate_limit(_client_identifier(request, supplied_key))


def _enforce_rate_limit(identifier: str) -> None:
    now = time.monotonic()
    window = _rate_limit_window_seconds()
    limit = _rate_limit_requests()
    bucket = _RATE_LIMIT_BUCKETS[identifier]
    while bucket and now - bucket[0] >= window:
        bucket.popleft()
    if len(bucket) >= limit:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    bucket.append(now)


def _reset_rate_limit_state() -> None:
    _RATE_LIMIT_BUCKETS.clear()


app = FastAPI(title="Trading Signal Engine", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/whitelist/search")
def search_whitelist(q: str = "") -> dict[str, Any]:
    keyword = q.strip().upper()
    results = []
    for entry in WHITELIST:
        candidates = [entry.ticker, entry.name.upper(), *entry.aliases]
        if not keyword or any(keyword in candidate for candidate in candidates):
            results.append(_to_jsonable(entry))
    return {"results": results}


@app.post("/api/workbench/analyze", dependencies=[Depends(_authenticate_workbench)])
def analyze(request: AnalyzeRequest) -> dict[str, Any]:
    try:
        analysis = analyze_workbench(
            AnalysisInput(
                ticker=request.ticker,
                capital_amount=request.capital_amount,
                target_return_pct=request.target_return_pct,
                target_period_days=request.target_period_days,
                max_loss_pct=request.max_loss_pct,
            ),
            offline=request.offline,
        )
    except WhitelistError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail="Analysis failed unexpectedly") from error
    return {"analysis": _to_jsonable(analysis)}


def main() -> int:
    uvicorn.run(
        "ai.stock_signal.server:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        reload=os.getenv("RELOAD", "0") == "1",
    )
    return 0


def _to_jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _to_jsonable(asdict(value))
    if isinstance(value, dict):
        return {key: _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_to_jsonable(item) for item in value]
    return value


if __name__ == "__main__":
    raise SystemExit(main())
