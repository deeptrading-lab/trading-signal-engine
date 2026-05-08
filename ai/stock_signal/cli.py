from __future__ import annotations

import argparse

from .engine import analyze_ticker
from .models import Timeframe
from .render import render_text


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a low-cost stock decision brief.")
    parser.add_argument("ticker", help="US stock or ETF ticker, e.g. AAPL")
    parser.add_argument(
        "--timeframe",
        choices=[item.value for item in Timeframe],
        default=Timeframe.SWING.value,
        help="Decision timeframe. Default: SWING",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Use deterministic synthetic prices. Useful when network is unavailable.",
    )
    args = parser.parse_args()

    brief = analyze_ticker(
        args.ticker,
        timeframe=Timeframe(args.timeframe),
        offline=args.offline,
    )
    print(render_text(brief))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
