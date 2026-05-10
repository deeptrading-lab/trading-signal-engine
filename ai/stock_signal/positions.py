from __future__ import annotations

from .models import PositionState, Trade


def calculate_position_state(trades: list[Trade], *, market_price: float) -> PositionState:
    quantity = 0.0
    cost_basis = 0.0
    realized_pnl = 0.0

    for trade in trades:
        side = trade.side.strip().upper()
        if trade.quantity <= 0 or trade.price <= 0:
            raise ValueError("trade quantity and price must be positive")

        if side == "BUY":
            quantity += trade.quantity
            cost_basis += trade.quantity * trade.price + trade.fee
        elif side == "SELL":
            if trade.quantity > quantity:
                raise ValueError("sell quantity cannot exceed current position")
            average_price = cost_basis / quantity if quantity else 0.0
            realized_pnl += (trade.price - average_price) * trade.quantity - trade.fee
            cost_basis -= average_price * trade.quantity
            quantity -= trade.quantity
        else:
            raise ValueError("trade side must be BUY or SELL")

    average_price = cost_basis / quantity if quantity else None
    market_value = quantity * market_price
    unrealized_pnl = (market_price - average_price) * quantity if average_price is not None else 0.0
    return PositionState(
        quantity=round(quantity, 8),
        average_price=round(average_price, 4) if average_price is not None else None,
        realized_pnl=round(realized_pnl, 2),
        market_value=round(market_value, 2),
        unrealized_pnl=round(unrealized_pnl, 2),
    )
