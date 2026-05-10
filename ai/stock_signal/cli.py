from __future__ import annotations

import argparse
import sys

from .engine import analyze_ticker
from .models import AnalysisInput, Timeframe
from .render import render_text, render_workbench_text
from .workbench import analyze_workbench


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "workbench":
        return _main_workbench(sys.argv[2:])

    parser = argparse.ArgumentParser(description="저비용 종목 판단 요약을 생성합니다.")
    parser.add_argument("ticker", help="미국 주식/ETF ticker, 예: AAPL")
    parser.add_argument(
        "--timeframe",
        choices=[item.value for item in Timeframe],
        default=Timeframe.SWING.value,
        help="분석 기간. 기본값: SWING",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="네트워크 없이 고정 샘플 가격을 사용합니다.",
    )
    args = parser.parse_args()

    brief = analyze_ticker(
        args.ticker,
        timeframe=Timeframe(args.timeframe),
        offline=args.offline,
    )
    print(render_text(brief))
    return 0


def _main_workbench(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="AI 시그널 워크벤치 분석을 생성합니다.")
    parser.add_argument("ticker", help="화이트리스트 ticker: AAPL, BTC, BTC-USD")
    parser.add_argument("--capital", type=float, required=True, help="투입 자본금(USD)")
    parser.add_argument("--target-return", type=float, required=True, help="목표 수익률(%)")
    parser.add_argument("--target-days", type=int, required=True, help="목표 기간(일)")
    parser.add_argument("--max-loss", type=float, default=2.0, help="거래당 최대 손실률(%)")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="네트워크 없이 고정 샘플 가격을 사용합니다.",
    )
    args = parser.parse_args(argv)

    analysis = analyze_workbench(
        AnalysisInput(
            ticker=args.ticker,
            capital_amount=args.capital,
            target_return_pct=args.target_return,
            target_period_days=args.target_days,
            max_loss_pct=args.max_loss,
        ),
        offline=args.offline,
    )
    print(render_workbench_text(analysis))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
