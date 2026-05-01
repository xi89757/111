from __future__ import annotations

from datetime import datetime, timezone

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from ..logging_setup import get_logger
from .base import Exchange, Market, OrderRequest, OrderResult, Quote

log = get_logger(__name__)

GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API = "https://clob.polymarket.com"


class PolymarketClient(Exchange):
    name = "polymarket"

    def __init__(self) -> None:
        self._http = httpx.AsyncClient(timeout=20.0, headers={"User-Agent": "trader/0.1"})

    async def close(self) -> None:
        await self._http.aclose()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def _get(self, base: str, path: str, **params) -> dict | list:
        r = await self._http.get(f"{base}{path}", params=params)
        r.raise_for_status()
        return r.json()

    async def list_markets(self, *, limit: int = 100, active_only: bool = True) -> list[Market]:
        params: dict = {"limit": limit, "order": "volume24hr", "ascending": False}
        if active_only:
            params.update({"active": "true", "closed": "false", "archived": "false"})
        data = await self._get(GAMMA_API, "/markets", **params)
        rows = data if isinstance(data, list) else data.get("data", [])
        markets: list[Market] = []
        for m in rows:
            try:
                end = m.get("endDate")
                end_dt = datetime.fromisoformat(end.replace("Z", "+00:00")) if end else None
                outcomes_raw = m.get("outcomes") or '["Yes","No"]'
                if isinstance(outcomes_raw, str):
                    import json
                    outcomes = json.loads(outcomes_raw)
                else:
                    outcomes = outcomes_raw
                markets.append(
                    Market(
                        exchange=self.name,
                        market_id=str(m.get("conditionId") or m.get("id")),
                        question=m.get("question", ""),
                        outcomes=outcomes,
                        end_date=end_dt,
                        category=m.get("category"),
                        volume=float(m.get("volume", 0) or 0),
                        liquidity=float(m.get("liquidity", 0) or 0),
                    )
                )
            except Exception as e:
                log.warning("market_parse_failed", err=str(e))
        return markets

    async def get_quote(self, market_id: str, outcome: str = "Yes") -> Quote:
        # Use CLOB midpoint endpoint by token; fall back to gamma if needed.
        # For MVP, query gamma market by conditionId and read outcomePrices.
        data = await self._get(GAMMA_API, "/markets", condition_ids=market_id)
        rows = data if isinstance(data, list) else data.get("data", [])
        if not rows:
            raise ValueError(f"market not found: {market_id}")
        m = rows[0]
        import json
        outcomes = json.loads(m["outcomes"]) if isinstance(m.get("outcomes"), str) else m.get("outcomes", [])
        prices = json.loads(m["outcomePrices"]) if isinstance(m.get("outcomePrices"), str) else m.get("outcomePrices", [])
        idx = outcomes.index(outcome) if outcome in outcomes else 0
        yes_p = float(prices[idx]) if idx < len(prices) else 0.5
        no_p = 1.0 - yes_p
        # gamma doesn't expose bid/ask cleanly; use mid as both, spread=0 for MVP
        return Quote(
            market_id=market_id,
            outcome=outcome,
            yes_price=yes_p,
            no_price=no_p,
            bid=yes_p,
            ask=yes_p,
            spread=0.0,
            timestamp=datetime.now(timezone.utc),
        )

    async def place_order(self, req: OrderRequest) -> OrderResult:
        raise NotImplementedError(
            "Live Polymarket trading not implemented in MVP. Use PaperBroker."
        )
