from __future__ import annotations

import json
import os
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from .cli import SampleNewsProvider
from .ingestion import NewsIngestionService
from .news import build_news_feature
from .openai_news import OpenAINewsProvider
from .repository import NewsRepository, create_repository_from_env
from .watchlist import require_watchlist_symbol

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None


class KrStockNewsHandler(BaseHTTPRequestHandler):
    repository: NewsRepository

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._send_json({"ok": True, "service": "kr-stock-news"})
            return
        try:
            query = parse_qs(parsed.query)
            if parsed.path == "/api/kr-stocks/news/daily":
                self._get_daily(query)
                return
            if parsed.path == "/api/kr-stocks/news/feature":
                self._get_feature(query)
                return
        except (ValueError, RuntimeError) as error:
            self._send_json({"error": str(error)}, status=400)
            return
        self._send_json({"error": "not found"}, status=404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/kr-stocks/news/refresh":
            self._send_json({"error": "not found"}, status=404)
            return
        try:
            payload = self._read_json_body()
            symbol = str(payload.get("symbol") or "")
            provider_name = str(payload.get("provider") or "openai").lower()
            if provider_name not in {"openai", "sample"}:
                raise ValueError("provider must be openai or sample")
            provider = OpenAINewsProvider() if provider_name == "openai" else SampleNewsProvider()
            result = NewsIngestionService(self.repository, provider).ingest_symbol(
                symbol,
                score_date=str(payload["score_date"]) if payload.get("score_date") else None,
            )
        except (ValueError, RuntimeError, json.JSONDecodeError) as error:
            self._send_json({"error": str(error)}, status=400)
            return
        self._send_json(asdict(result), status=201)

    def _get_daily(self, query: dict[str, list[str]]) -> None:
        symbol = require_watchlist_symbol(_query_value(query, "symbol")).symbol
        date = _query_value(query, "date", required=False)
        scores = self.repository.fetch_daily_news_scores(symbol, limit=366 if date else 10)
        if date:
            scores = [score for score in scores if score.date == date]
        self._send_json({"symbol": symbol, "scores": [asdict(score) for score in scores]})

    def _get_feature(self, query: dict[str, list[str]]) -> None:
        symbol = require_watchlist_symbol(_query_value(query, "symbol")).symbol
        lookback_days = int(_query_value(query, "lookback_days", default="10"))
        if not 1 <= lookback_days <= 10:
            raise ValueError("lookback_days must be between 1 and 10")
        scores = self.repository.fetch_daily_news_scores(symbol, limit=lookback_days)
        self._send_json(asdict(build_news_feature(symbol, scores)))

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length > 0 else b"{}"
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object")
        return payload

    def _send_json(self, payload: object, *, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._send_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_cors_headers(self) -> None:
        origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")
        self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def log_message(self, format: str, *args: Any) -> None:
        return


def _query_value(
    query: dict[str, list[str]],
    name: str,
    *,
    default: str | None = None,
    required: bool = True,
) -> str:
    value = query.get(name, [default])[0]
    if required and not value:
        raise ValueError(f"{name} is required")
    return value or ""


def main() -> int:
    if load_dotenv is not None:
        load_dotenv(".env", override=False)
        load_dotenv(".env.local", override=True)
    repository = create_repository_from_env()
    repository.initialize()
    KrStockNewsHandler.repository = repository
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("KR_STOCK_PORT", "8766"))
    server = ThreadingHTTPServer((host, port), KrStockNewsHandler)
    print(f"Korean stock news engine listening on http://{host}:{port}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
