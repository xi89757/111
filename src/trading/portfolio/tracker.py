from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class Position:
    market_id: str
    outcome: str
    side: str  # YES | NO
    shares: float
    avg_price: float
    cost_basis: float
    opened_at: str

    def mark_to_market(self, yes_price: float) -> float:
        price = yes_price if self.side == "YES" else (1.0 - yes_price)
        return self.shares * price


@dataclass
class Fill:
    timestamp: str
    market_id: str
    side: str
    shares: float
    price: float
    notional: float


@dataclass
class PortfolioState:
    cash: float
    positions: dict[str, Position] = field(default_factory=dict)
    fills: list[Fill] = field(default_factory=list)

    def exposure(self) -> float:
        return sum(p.cost_basis for p in self.positions.values())

    def equity(self, prices: dict[str, float]) -> float:
        mtm = sum(
            p.mark_to_market(prices.get(p.market_id, p.avg_price))
            for p in self.positions.values()
        )
        return self.cash + mtm

    @classmethod
    def load(cls, path: Path, starting_cash: float) -> "PortfolioState":
        if not path.exists():
            return cls(cash=starting_cash)
        raw = json.loads(path.read_text())
        positions = {k: Position(**v) for k, v in raw.get("positions", {}).items()}
        fills = [Fill(**f) for f in raw.get("fills", [])]
        return cls(cash=raw["cash"], positions=positions, fills=fills)

    def save(self, path: Path) -> None:
        payload = {
            "cash": self.cash,
            "positions": {k: asdict(v) for k, v in self.positions.items()},
            "fills": [asdict(f) for f in self.fills],
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }
        path.write_text(json.dumps(payload, indent=2))
