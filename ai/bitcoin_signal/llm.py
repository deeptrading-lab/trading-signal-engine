from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .config import load_llm_settings
from .models import BitcoinAllocationBrief, NewsSnapshot


class LLMProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class LLMBrief:
    enabled: bool
    provider: str
    model: str
    status: str
    summary_ko: str
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    estimated_cost_usd: float | None
    sources: list[str]
    error: str | None


def generate_llm_brief(brief: BitcoinAllocationBrief, provider: str) -> LLMBrief:
    normalized = provider.strip().lower()
    if normalized in {"none", ""}:
        raise LLMProviderError("LLM provider is disabled")
    if normalized == "openai":
        return _generate_openai_brief(brief)
    if normalized in {"claude", "anthropic"}:
        return _generate_anthropic_brief(brief)
    raise LLMProviderError("unsupported LLM provider")


def fetch_openai_bitcoin_news_snapshot() -> NewsSnapshot:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise LLMProviderError("OPENAI_API_KEY is not configured")

    settings = load_llm_settings()
    payload = {
        "model": settings.news_model,
        "tools": [{"type": "web_search"}],
        "tool_choice": "auto",
        "input": (
            "Search the web for the latest Bitcoin-only market news. "
            "Focus on ETF flows, regulation, macro events, institutional demand, and major exchange/security incidents. "
            "Return minified JSON only, no markdown. Schema: "
            "{\"sentiment\":\"bullish|neutral|bearish\",\"summary_ko\":\"Korean beginner summary under 450 chars\","
            "\"sources\":[\"2-4 source names or URLs\"]}"
        ),
        "max_output_tokens": 700,
    }
    response = _post_json(
        "https://api.openai.com/v1/responses",
        payload,
        headers={"Authorization": f"Bearer {api_key}"},
    )
    usage = response.get("usage") or {}
    input_tokens = _optional_int(usage.get("input_tokens"))
    output_tokens = _optional_int(usage.get("output_tokens"))
    text = _extract_openai_text(response)
    parsed = _parse_news_json(text)
    sentiment = str(parsed.get("sentiment") or _extract_sentiment(text))
    sources = _normalize_sources(parsed.get("sources")) or _extract_sources(text)
    return NewsSnapshot(
        summary_ko=str(parsed.get("summary_ko") or _extract_summary(text)),
        sentiment=sentiment,
        source_count=len(sources),
        sources=sources,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost_usd=_estimate_openai_cost(settings.news_model, input_tokens, output_tokens),
    )


def _generate_openai_brief(brief: BitcoinAllocationBrief) -> LLMBrief:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise LLMProviderError("OPENAI_API_KEY is not configured")

    settings = load_llm_settings()
    payload = {
        "model": settings.brief_model,
        "input": _prompt(brief),
        "max_output_tokens": 260,
    }
    response = _post_json(
        "https://api.openai.com/v1/responses",
        payload,
        headers={"Authorization": f"Bearer {api_key}"},
    )
    usage = response.get("usage") or {}
    input_tokens = _optional_int(usage.get("input_tokens"))
    output_tokens = _optional_int(usage.get("output_tokens"))
    total_tokens = _optional_int(usage.get("total_tokens"))
    return LLMBrief(
        enabled=True,
        provider="openai",
        model=str(response.get("model") or settings.brief_model),
        status="ok",
        summary_ko=_extract_openai_text(response),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        estimated_cost_usd=_estimate_openai_cost(settings.brief_model, input_tokens, output_tokens),
        sources=[],
        error=None,
    )


def _generate_anthropic_brief(brief: BitcoinAllocationBrief) -> LLMBrief:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise LLMProviderError("ANTHROPIC_API_KEY is not configured")

    settings = load_llm_settings()
    payload = {
        "model": settings.anthropic_brief_model,
        "max_tokens": 260,
        "system": "You explain Bitcoin allocation engine output in concise Korean. Do not change action, sizing, score, or risk thresholds.",
        "messages": [{"role": "user", "content": _prompt(brief)}],
    }
    response = _post_json(
        "https://api.anthropic.com/v1/messages",
        payload,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
    )
    usage = response.get("usage") or {}
    input_tokens = _optional_int(usage.get("input_tokens"))
    output_tokens = _optional_int(usage.get("output_tokens"))
    return LLMBrief(
        enabled=True,
        provider="claude",
        model=str(response.get("model") or settings.anthropic_brief_model),
        status="ok",
        summary_ko=_extract_anthropic_text(response),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=(input_tokens + output_tokens) if input_tokens is not None and output_tokens is not None else None,
        estimated_cost_usd=None,
        sources=[],
        error=None,
    )


def _prompt(brief: BitcoinAllocationBrief) -> str:
    return "\n".join(
        [
            "아래 비트코인 배분 엔진 결과를 초보 투자자가 이해할 수 있게 한국어로 4문장 이내 요약해줘.",
            "중요: action, sizing, score, risk-off 조건을 바꾸거나 새 수치를 만들지 마.",
            f"action={brief.action.value}",
            f"confidence={brief.confidence.value}",
            f"score={brief.score}/100",
            f"reference_price={brief.reference_price:.2f}",
            f"sizing={brief.sizing.sizing_label_ko}",
            f"sizing_detail={brief.sizing.sizing_detail_ko}",
            f"risk_off={brief.risk_off_condition}",
            "reasons=" + "; ".join(brief.reasons[:3]),
            "risks=" + "; ".join(brief.risks[:2]),
        ]
    )


def _post_json(url: str, payload: dict[str, Any], *, headers: dict[str, str]) -> dict[str, Any]:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urlopen(request, timeout=20) as response:
            parsed = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise LLMProviderError(f"LLM provider HTTP {error.code}: {_redact(body)}") from error
    except (OSError, URLError, json.JSONDecodeError) as error:
        raise LLMProviderError(f"LLM provider unavailable: {error}") from error
    if not isinstance(parsed, dict):
        raise LLMProviderError("LLM provider returned an unexpected payload")
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
    raise LLMProviderError("OpenAI response did not include text output")


def _extract_anthropic_text(payload: dict[str, Any]) -> str:
    content = payload.get("content")
    if isinstance(content, list):
        parts = [item.get("text") for item in content if isinstance(item, dict) and isinstance(item.get("text"), str)]
        if parts:
            return "\n".join(parts).strip()
    raise LLMProviderError("Anthropic response did not include text output")


def _extract_sentiment(text: str) -> str:
    lowered = text.lower()
    if "bearish" in lowered:
        return "bearish"
    if "bullish" in lowered:
        return "bullish"
    return "neutral"


def _parse_news_json(text: str) -> dict[str, Any]:
    stripped = text.strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return {}
    try:
        parsed = json.loads(stripped[start : end + 1])
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _extract_summary(text: str) -> str:
    for line in text.splitlines():
        if line.lower().startswith("summary:"):
            return line.split(":", 1)[1].strip()
    return text.strip()


def _normalize_sources(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()][:4]


def _extract_sources(text: str) -> list[str]:
    for line in text.splitlines():
        if line.lower().startswith("sources:"):
            raw = line.split(":", 1)[1]
            return [item.strip(" -") for item in raw.split(",") if item.strip(" -")][:4]
    return []


def _optional_int(value: Any) -> int | None:
    return int(value) if isinstance(value, int | float) else None


def _estimate_openai_cost(model: str, input_tokens: int | None, output_tokens: int | None) -> float | None:
    if input_tokens is None or output_tokens is None:
        return None
    pricing = {
        "gpt-5.4-nano": (0.20, 1.25),
        "gpt-5.4-mini": (0.75, 4.50),
        "gpt-5.4": (2.50, 15.00),
    }
    input_per_m, output_per_m = pricing.get(model, pricing.get(model.split(":")[0], (None, None)))
    if input_per_m is None or output_per_m is None:
        return None
    return round((input_tokens / 1_000_000 * input_per_m) + (output_tokens / 1_000_000 * output_per_m), 8)


def _redact(text: str) -> str:
    redacted = text
    for key_name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        secret = os.getenv(key_name)
        if secret:
            redacted = redacted.replace(secret, "[redacted]")
    return redacted
