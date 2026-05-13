from __future__ import annotations

from .models import AnalysisInput, RiskTier, TargetFeasibility, TechnicalSnapshot, WhitelistEntry


def annualized_target_return(target_return_pct: float, target_period_days: int) -> float:
    if target_period_days <= 0:
        raise ValueError("target_period_days must be positive")
    return ((1.0 + target_return_pct / 100.0) ** (365.0 / target_period_days) - 1.0) * 100.0


def evaluate_target_feasibility(
    analysis_input: AnalysisInput,
    technicals: TechnicalSnapshot,
    whitelist_entry: WhitelistEntry,
) -> tuple[TargetFeasibility, float]:
    annualized = annualized_target_return(
        analysis_input.target_return_pct,
        analysis_input.target_period_days,
    )
    volatility = technicals.volatility_20d or 40.0

    if annualized <= 25:
        score = 0
    elif annualized <= 80:
        score = 1
    else:
        score = 2

    if annualized > max(25.0, volatility * 1.5):
        score += 1
    if whitelist_entry.risk_tier in {RiskTier.HIGH, RiskTier.SPECULATIVE}:
        score += 1
    if technicals.return_20d is not None and technicals.return_20d < -8:
        score += 1

    if score <= 0:
        feasibility = TargetFeasibility.REALISTIC
    elif score <= 2:
        feasibility = TargetFeasibility.STRETCHED
    else:
        feasibility = TargetFeasibility.UNREALISTIC
    return feasibility, round(annualized, 2)
