from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from ..logging_setup import get_logger
from ..portfolio.tracker import Fill, PortfolioState, Position

log = get_logger(__name__)


class PaperBroker:
    """In-memory paper-trading broker. Fills at quoted price (no slippage model yet)."""

    def __init__(self, state: PortfolioState, state_path: Path) -> None:
        self.state = state
        self.state_path = state_path

    def execute(
        self,
        *,
        market_id: str,
        side: str,  # "YES" or "NO"
        notional_usd: float,
        yes_price: float,
    ) -> Fill | None:
        if notional_usd <= 0:
            return None
        price = yes_price if side == "YES" else (1.0 - yes_price)
        if price <= 0 or price >= 1:
            log.warning("paper_skip_bad_price", market=market_id, price=price)
            return None
        if notional_usd > self.state.cash:
            log.warning("paper_insufficient_cash", need=notional_usd, have=self.state.cash)
            notional_usd = self.state.cash
            if notional_usd <= 0:
                return None
        shares = notional_usd / price
        self.state.cash -= notional_usd

        existing = self.state.positions.get(market_id)
        if existing and existing.side == side:
            new_shares = existing.shares + shares
            new_cost = existing.cost_basis + notional_usd
            existing.shares = new_shares
            existing.avg_price = new_cost / new_shares
            existing.cost_basis = new_cost
        else:
            self.state.positions[market_id] = Position(
                market_id=market_id,
                outcome="Yes",
                side=side,
                shares=shares,
                avg_price=price,
                cost_basis=notional_usd,
                opened_at=datetime.now(timezone.utc).isoformat(),
            )

        fill = Fill(
            timestamp=datetime.now(timezone.utc).isoformat(),
            market_id=market_id,
            side=side,
            shares=shares,
            price=price,
            notional=notional_usd,
        )
        self.state.fills.append(fill)
        self.state.save(self.state_path)
        log.info(
            "paper_fill",
            market=market_id,
            side=side,
            shares=round(shares, 2),
            price=round(price, 3),
            notional=round(notional_usd, 2),
            cash_left=round(self.state.cash, 2),
            order_id=str(uuid.uuid4())[:8],
        )
        return fill
