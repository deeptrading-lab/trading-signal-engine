from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from .engine import analyze_bitcoin
from .llm import LLMProviderError, generate_llm_brief
from .models import Timeframe

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dependency exists in project requirements.
    load_dotenv = None


def _json_default(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if hasattr(value, "value"):
        return value.value
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


class BitcoinSignalHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._send_json({"ok": True})
            return
        if parsed.path != "/api/bitcoin/brief":
            self._send_json({"error": "not found"}, status=404)
            return

        query = parse_qs(parsed.query)
        symbol = query.get("symbol", ["BTC"])[0]
        timeframe = query.get("timeframe", [Timeframe.SWING.value])[0]
        offline = query.get("offline", ["true"])[0].lower() not in {"0", "false", "no"}

        try:
            brief = analyze_bitcoin(symbol, timeframe=Timeframe(timeframe), offline=offline)
        except ValueError as error:
            self._send_json({"error": str(error)}, status=400)
            return

        self._send_json(brief)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/bitcoin/brief":
            self._send_json({"error": "not found"}, status=404)
            return

        try:
            payload = self._read_json_body()
            symbol = str(payload.get("symbol") or "BTC")
            timeframe = Timeframe(str(payload.get("timeframe") or Timeframe.SWING.value))
            offline = _parse_bool(payload.get("offline"), default=False)
            llm_provider = str(payload.get("llm_provider") or "none")
            data_provider = str(payload.get("data_provider") or "none")
            cash_amount = _parse_optional_float(payload.get("cash_amount"))
            cash_currency = str(payload.get("cash_currency") or "KRW")
            btc_holding_amount = _parse_optional_float(payload.get("btc_holding_amount"))

            brief = analyze_bitcoin(
                symbol,
                timeframe=timeframe,
                offline=offline,
                cash_amount=cash_amount,
                cash_currency=cash_currency,
                btc_holding_amount=btc_holding_amount,
                data_provider=data_provider,
            )
        except (ValueError, json.JSONDecodeError) as error:
            self._send_json({"error": str(error)}, status=400)
            return

        payload = {"brief": brief, "llm": None}
        if llm_provider.lower() != "none":
            try:
                payload["llm"] = generate_llm_brief(brief, llm_provider)
            except LLMProviderError as error:
                payload["llm"] = {
                    "enabled": True,
                    "provider": llm_provider,
                    "model": None,
                    "status": "unavailable",
                    "summary_ko": "",
                    "input_tokens": None,
                    "output_tokens": None,
                    "total_tokens": None,
                    "estimated_cost_usd": None,
                    "sources": [],
                    "error": str(error),
                }
        self._send_json(payload)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object")
        return payload

    def _send_json(self, payload: Any, *, status: int = 200) -> None:
        body = json.dumps(payload, default=_json_default, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._send_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "http://localhost:3000")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")


def _parse_optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    parsed = float(value)
    if parsed < 0:
        raise ValueError("portfolio inputs must be non-negative")
    return parsed


def _parse_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off"}
    return bool(value)


def main() -> int:
    if load_dotenv is not None:
        load_dotenv(".env", override=False)
        load_dotenv(".env.local", override=True)
    server = ThreadingHTTPServer(("127.0.0.1", 8765), BitcoinSignalHandler)
    print("Bitcoin signal engine listening on http://127.0.0.1:8765")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
