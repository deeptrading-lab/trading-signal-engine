from __future__ import annotations

import json
import os
import threading
from datetime import date
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .ingestion import NewsProvider, NewsProviderError
from .models import Confidence, NewsItem
from .watchlist import require_watchlist_symbol


PROMPT_VERSION = "kr-stock-news-v1"
ALLOWED_RISK_TAGS = {
    "earnings",
    "guidance",
    "macro",
    "fx",
    "supply_chain",
    "regulation",
    "labor",
    "geopolitics",
    "product",
    "customer",
    "sector",
    "valuation",
    "liquidity",
}
_budget_lock = threading.Lock()
_budget_date: str | None = None
_reserved_cost_usd = 0.0


class OpenAINewsProvider(NewsProvider):
    def __init__(self, *, model: str | None = None, timeout_seconds: float = 30.0) -> None:
        self.model = model or os.getenv("OPENAI_NEWS_MODEL", "gpt-4.1-mini")
        self.timeout_seconds = timeout_seconds

    def fetch_news_items(self, symbol: str) -> list[NewsItem]:
        watch = require_watchlist_symbol(symbol)
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise NewsProviderError("OPENAI_API_KEY is not configured")
        reservation = _reserve_daily_budget()

        try:
            response = _post_json(
                "https://api.openai.com/v1/responses",
                {
                    "model": self.model,
                    "tools": [{"type": "web_search"}],
                    "tool_choice": "auto",
                    "input": _build_prompt(watch.symbol, watch.name_ko),
                    "max_output_tokens": 1200,
                },
                headers={"Authorization": f"Bearer {api_key}"},
                timeout_seconds=self.timeout_seconds,
            )
        except Exception:
            _release_daily_budget(reservation)
            raise
        usage = response.get("usage") or {}
        parsed = _parse_json_text(_extract_openai_text(response))
        return _items_from_payload(
            parsed,
            expected_symbol=watch.symbol,
            model=str(response.get("model") or self.model),
            input_tokens=_optional_int(usage.get("input_tokens")),
            output_tokens=_optional_int(usage.get("output_tokens")),
        )


def _build_prompt(symbol: str, name_ko: str) -> str:
    today = date.today().isoformat()
    return (
        f"Today is {today}. Search Korean stock market news for {name_ko} ({symbol}) published today or within the last 3 days. "
        "Return JSON only. Do not include markdown. "
        "The JSON schema is: "
        '{"symbol":"string","as_of":"ISO-8601","items":[{'
        '"title":"string","source":"string","url":"string","published_at":"string|null",'
        '"summary_ko":"20-300 char Korean summary",'
        '"sentiment_score":-3,"impact_score":0,"relevance_score":0,'
        '"novelty":"NEW|REPEAT|UNKNOWN","risk_tags":["earnings"],'
        '"confidence":"LOW|MEDIUM|HIGH"}]}. '
        "Deduplicate repeated articles with the same title or URL. "
        "Score sentiment -3..3, impact 0..3, relevance 0..3. "
        "Use only these risk_tags values: earnings, guidance, macro, fx, supply_chain, regulation, labor, "
        "geopolitics, product, customer, sector, valuation, liquidity. "
        "If only older background articles are available, include them only when clearly relevant and set confidence LOW. "
        "Store only article metadata and summary, not full article body."
    )


def _post_json(url: str, payload: dict[str, Any], *, headers: dict[str, str], timeout_seconds: float) -> dict[str, Any]:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            parsed = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise NewsProviderError(f"OpenAI news provider HTTP {error.code}: {_redact(body)}") from error
    except (OSError, URLError, json.JSONDecodeError) as error:
        raise NewsProviderError(f"OpenAI news provider unavailable: {error}") from error
    if not isinstance(parsed, dict):
        raise NewsProviderError("OpenAI news provider returned an unexpected payload")
    return parsed


def _extract_openai_text(payload: dict[str, Any]) -> str:
    if isinstance(payload.get("output_text"), str):
        return str(payload["output_text"]).strip()
    output = payload.get("output")
    if isinstance(output, list):
        parts: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if isinstance(block, dict) and isinstance(block.get("text"), str):
                    parts.append(block["text"])
        if parts:
            return "\n".join(parts).strip()
    raise NewsProviderError("OpenAI response did not include text output")


def _parse_json_text(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as error:
        raise NewsProviderError("OpenAI news response was not valid JSON") from error
    if not isinstance(parsed, dict):
        raise NewsProviderError("OpenAI news response JSON must be an object")
    return parsed


def _items_from_payload(
    payload: dict[str, Any],
    *,
    expected_symbol: str,
    model: str,
    input_tokens: int | None,
    output_tokens: int | None,
) -> list[NewsItem]:
    symbol = str(payload.get("symbol") or expected_symbol)
    if symbol != expected_symbol:
        raise NewsProviderError(f"OpenAI news response symbol mismatch: {symbol}")
    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        raise NewsProviderError("OpenAI news response missing items list")

    items: list[NewsItem] = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        risk_tags = raw.get("risk_tags") if isinstance(raw.get("risk_tags"), list) else []
        normalized_risk_tags = tuple(str(tag) for tag in risk_tags)
        unknown_tags = set(normalized_risk_tags) - ALLOWED_RISK_TAGS
        if unknown_tags:
            raise NewsProviderError(f"OpenAI news response contains unknown risk tags: {sorted(unknown_tags)}")
        confidence_value = str(raw.get("confidence") or "MEDIUM")
        try:
            confidence = Confidence(confidence_value)
        except ValueError:
            confidence = Confidence.LOW
        items.append(
            NewsItem(
                symbol=expected_symbol,
                title=str(raw.get("title") or ""),
                summary_ko=str(raw.get("summary_ko") or ""),
                sentiment_score=int(raw.get("sentiment_score") or 0),
                impact_score=int(raw.get("impact_score") or 0),
                relevance_score=int(raw.get("relevance_score") or 0),
                source=str(raw.get("source") or ""),
                url=str(raw.get("url") or ""),
                published_at=str(raw.get("published_at")) if raw.get("published_at") is not None else None,
                novelty=str(raw.get("novelty") or "UNKNOWN"),
                risk_tags=normalized_risk_tags,
                confidence=confidence,
                prompt_version=PROMPT_VERSION,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
        )
    return items


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _reserve_daily_budget() -> float:
    global _budget_date, _reserved_cost_usd
    today = date.today().isoformat()
    daily_limit = _non_negative_float_env("OPENAI_DAILY_COST_LIMIT_USD", 0.50)
    reservation = _non_negative_float_env("OPENAI_NEWS_MAX_REQUEST_COST_USD", 0.10)
    with _budget_lock:
        if _budget_date != today:
            _budget_date = today
            _reserved_cost_usd = 0.0
        if _reserved_cost_usd + reservation > daily_limit:
            raise NewsProviderError(
                f"OpenAI daily cost limit would be exceeded: "
                f"${_reserved_cost_usd + reservation:.2f} > ${daily_limit:.2f}"
            )
        _reserved_cost_usd += reservation
    return reservation


def _release_daily_budget(reservation: float) -> None:
    global _reserved_cost_usd
    with _budget_lock:
        _reserved_cost_usd = max(0.0, _reserved_cost_usd - reservation)


def _non_negative_float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    value = default if raw in (None, "") else float(raw)
    if value < 0:
        raise ValueError(f"{name} must be non-negative")
    return value


def _redact(text: str) -> str:
    return text.replace(os.getenv("OPENAI_API_KEY", ""), "[REDACTED]") if os.getenv("OPENAI_API_KEY") else text
