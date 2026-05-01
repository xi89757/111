from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass
class Market:
    exchange: str
    market_id: str
    question: str
    outcomes: list[str]
    end_date: datetime | None
    category: str | None = None
    volume: float = 0.0
    liquidity: float = 0.0


@dataclass
class Quote:
    market_id: str
    outcome: str
    yes_price: float
    no_price: float
    bid: float
    ask: float
    spread: float
    timestamp: datetime


@dataclass
class OrderRequest:
    market_id: str
    outcome: str
    side: str
    size: float
    limit_price: float


@dataclass
class OrderResult:
    order_id: str
    market_id: str
    outcome: str
    side: str
    filled_size: float
    avg_price: float
    status: str
    timestamp: datetime


class Exchange(ABC):
    name: str

    @abstractmethod
    async def list_markets(self, *, limit: int = 100, active_only: bool = True) -> list[Market]: ...

    @abstractmethod
    async def get_quote(self, market_id: str, outcome: str) -> Quote: ...

    @abstractmethod
    async def place_order(self, req: OrderRequest) -> OrderResult: ...

    async def close(self) -> None:
        return None
