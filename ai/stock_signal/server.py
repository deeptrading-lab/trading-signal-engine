from __future__ import annotations

import os
from dataclasses import asdict, is_dataclass
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
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


def _cors_origins() -> list[str]:
    configured = os.getenv("CORS_ORIGINS")
    if configured:
        return [origin.strip() for origin in configured.split(",") if origin.strip()]
    return ["http://localhost:3000", "http://127.0.0.1:3000"]


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


@app.post("/api/workbench/analyze")
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
        raise HTTPException(status_code=500, detail=str(error)) from error
    return {"analysis": _to_jsonable(analysis)}


def main() -> int:
    uvicorn.run(
        "ai.stock_signal.server:app",
        host=os.getenv("HOST", "127.0.0.1"),
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
