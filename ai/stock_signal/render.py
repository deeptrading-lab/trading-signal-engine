from __future__ import annotations

from .models import StockDecisionBrief, WorkbenchAnalysis


_LABELS = {
    "ACTIONABLE_LONG": "매수 검토 가능",
    "CONDITIONAL_LONG": "조건부 매수 검토",
    "HOLD_MONITOR": "관망",
    "REDUCE_RISK": "리스크 축소",
    "AVOID": "진입 회피",
    "ACTIONABLE_BUY": "매수 검토 가능",
    "CONDITIONAL_BUY": "조건부 매수 검토",
    "HOLD": "관망",
    "PARTIAL_SELL": "일부 매도 검토",
    "SELL": "매도 검토",
    "LOW": "낮음",
    "MEDIUM": "보통",
    "HIGH": "높음",
    "REALISTIC": "현실적",
    "STRETCHED": "공격적",
    "UNREALISTIC": "현실성 낮음",
    "SHORT_TERM": "단기",
    "SWING": "스윙",
    "POSITION": "포지션",
    "BULLISH": "상승 우위",
    "NEUTRAL": "중립",
    "BEARISH": "하락 우위",
}


def ko(value: object) -> str:
    raw = getattr(value, "value", value)
    return _LABELS.get(str(raw), str(raw))


def render_text(brief: StockDecisionBrief) -> str:
    rr = f"1 : {brief.risk_reward:.2f}" if brief.risk_reward is not None else "N/A"
    upside = f"{brief.upside_reference_pct:+.1f}%" if brief.upside_reference_pct is not None else "N/A"
    downside = f"{brief.downside_reference_pct:+.1f}%" if brief.downside_reference_pct is not None else "N/A"

    lines = [
        f"{brief.ticker} 판단 요약",
        "",
        f"판단: {ko(brief.action)}",
        f"확신도: {ko(brief.confidence)}",
        f"점수: {brief.score}/100",
        f"분석 기간: {ko(brief.timeframe)}",
        f"기준 가격: {brief.reference_price:.2f}",
        f"데이터 출처: {brief.data_quality.source}",
        "",
        "진입 조건",
        f"- {brief.entry_condition}",
        "",
        "무효 조건",
        f"- {brief.invalidation}",
        "",
        "위험 / 보상",
        f"- 하방 기준: {downside}",
        f"- 상방 기준: {upside}",
        f"- 예상 손익비: {rr}",
        "",
        "주요 근거",
        *[f"- {reason}" for reason in brief.reasons],
        "",
        "주요 리스크",
        *[f"- {risk}" for risk in brief.risks],
        "",
        brief.disclaimer,
    ]
    return "\n".join(lines)


def render_workbench_text(analysis: WorkbenchAnalysis) -> str:
    risk = analysis.risk_plan
    rr = f"1 : {risk.risk_reward_ratio:.2f}" if risk.risk_reward_ratio is not None else "N/A"
    position_lines: list[str] = []
    if analysis.position is not None:
        position = analysis.position
        average_price = f"{position.average_price:.2f}" if position.average_price is not None else "N/A"
        position_lines = [
            "",
            "보유 현황",
            f"- 수량: {position.quantity:g}",
            f"- 평균단가: {average_price}",
            f"- 평가금액: ${position.market_value:,.2f}",
            f"- 실현손익: ${position.realized_pnl:,.2f}",
            f"- 미실현손익: ${position.unrealized_pnl:,.2f}",
        ]
    warning_lines = (
        [
            "",
            "데이터 경고",
            *[f"- {warning}" for warning in analysis.warnings],
        ]
        if analysis.warnings
        else []
    )
    lines = [
        f"{analysis.whitelist_entry.name} ({analysis.whitelist_entry.ticker}) 분석 워크벤치",
        "",
        f"최종 판단: {ko(analysis.action)}",
        f"엔진 판단: {ko(analysis.brief.action)}",
        f"확신도: {ko(analysis.brief.confidence)}",
        f"점수: {analysis.brief.score}/100",
        f"목표 현실성: {ko(analysis.feasibility)}",
        f"연환산 목표 수익률: {analysis.annualized_target_return_pct:.1f}%",
        f"기준 가격: {analysis.brief.reference_price:.2f}",
        f"데이터 출처: {analysis.brief.data_quality.source}",
        "",
        "리스크 계획",
        f"- 권장 매수 금액: ${risk.suggested_buy_amount:,.2f}",
        f"- 권장 수량: {risk.suggested_share_qty:g}",
        f"- 진입 기준가: {risk.entry_price:.2f}",
        f"- 당일 익절가: {risk.take_profit_price_for_day:.2f}",
        f"- 당일 손절가: {risk.stop_loss_price_for_day:.2f}",
        f"- 손절 시 예상 손실: ${risk.expected_loss_if_stopped:,.2f}",
        f"- 익절 시 예상 이익: ${risk.expected_gain_if_take_profit:,.2f}",
        f"- 예상 손익비: {rr}",
        *position_lines,
        "",
        "기간별 흐름",
        *[
            f"- {item.label}: {item.return_pct:+.2f}% ({ko(item.direction)}), 최대 낙폭 {item.max_drawdown_pct:.2f}%"
            for item in analysis.horizons
        ],
        "",
        "주요 근거",
        *[f"- {reason}" for reason in analysis.brief.reasons],
        "",
        "주요 리스크",
        *[f"- {risk_item}" for risk_item in analysis.brief.risks],
        *warning_lines,
        "",
        analysis.brief.disclaimer,
    ]
    return "\n".join(lines)
