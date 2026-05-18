from __future__ import annotations

import argparse

from .engine import analyze_bitcoin
from .models import Timeframe
from .render import render_text


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a low-cost Bitcoin allocation brief.")
    parser.add_argument("symbol", nargs="?", default="BTC", help="Bitcoin symbol. Supported: BTC, BTC-USD, bitcoin")
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
    parser.add_argument("--cash-amount", type=float, default=None, help="Request-scoped available cash amount.")
    parser.add_argument("--cash-currency", choices=["KRW", "USD"], default="KRW", help="Cash currency.")
    parser.add_argument("--btc-holding", type=float, default=None, help="Request-scoped BTC holding amount.")
    args = parser.parse_args()

    brief = analyze_bitcoin(
        args.symbol,
        timeframe=Timeframe(args.timeframe),
        offline=args.offline,
        cash_amount=args.cash_amount,
        cash_currency=args.cash_currency,
        btc_holding_amount=args.btc_holding,
    )
    print(render_text(brief))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
