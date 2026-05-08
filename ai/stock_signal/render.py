from __future__ import annotations

from .models import StockDecisionBrief


def render_text(brief: StockDecisionBrief) -> str:
    rr = f"1 : {brief.risk_reward:.2f}" if brief.risk_reward is not None else "N/A"
    upside = f"{brief.upside_reference_pct:+.1f}%" if brief.upside_reference_pct is not None else "N/A"
    downside = f"{brief.downside_reference_pct:+.1f}%" if brief.downside_reference_pct is not None else "N/A"

    lines = [
        f"{brief.ticker} Decision Brief",
        "",
        f"Action: {brief.action.value}",
        f"Conviction: {brief.confidence.value}",
        f"Score: {brief.score}/100",
        f"Timeframe: {brief.timeframe.value}",
        f"Reference price: {brief.reference_price:.2f}",
        f"Data source: {brief.data_quality.source}",
        "",
        "Entry condition",
        f"- {brief.entry_condition}",
        "",
        "Invalidation",
        f"- {brief.invalidation}",
        "",
        "Risk / Reward",
        f"- Downside reference: {downside}",
        f"- Upside reference: {upside}",
        f"- Approx R/R: {rr}",
        "",
        "Why",
        *[f"- {reason}" for reason in brief.reasons],
        "",
        "Risks",
        *[f"- {risk}" for risk in brief.risks],
        "",
        brief.disclaimer,
    ]
    return "\n".join(lines)
