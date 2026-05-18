from __future__ import annotations

from .models import BitcoinAllocationBrief


def render_text(brief: BitcoinAllocationBrief) -> str:
    rr = f"1 : {brief.risk_range_ratio:.2f}" if brief.risk_range_ratio is not None else "N/A"
    upside = f"{brief.upside_reference_pct:+.1f}%" if brief.upside_reference_pct is not None else "N/A"
    downside = f"{brief.downside_reference_pct:+.1f}%" if brief.downside_reference_pct is not None else "N/A"

    lines = [
        "Bitcoin Allocation Brief",
        "",
        f"Action: {brief.action.value}",
        f"Conviction: {brief.confidence.value}",
        f"Score: {brief.score}/100",
        f"Timeframe: {brief.timeframe.value}",
        f"BTC reference price: {brief.reference_price:.2f}",
        f"Data source: {brief.data_quality.source}",
        "",
        "Sizing",
        f"- {brief.sizing.sizing_label_ko}",
        f"- {brief.sizing.sizing_detail_ko}",
        "",
        "Allocation condition",
        f"- {brief.allocation_condition}",
        "",
        "Risk-off condition",
        f"- {brief.risk_off_condition}",
        "",
        "Risk range",
        f"- Downside reference: {downside}",
        f"- Upside reference: {upside}",
        f"- Approx upside/downside: {rr}",
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
