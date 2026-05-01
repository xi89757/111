from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict
from pathlib import Path

from rich.console import Console
from rich.table import Table

from .analysis.llm import decide, screen_markets
from .config import settings
from .data.news import fetch_rss_all
from .exchanges.polymarket import PolymarketClient
from .execution.paper import PaperBroker
from .logging_setup import configure_logging, get_logger
from .portfolio.tracker import PortfolioState
from .risk.kelly import position_size_usd

console = Console()
log = get_logger(__name__)
STATE_PATH = Path("paper_state.json")


async def cmd_markets(limit: int) -> None:
    poly = PolymarketClient()
    try:
        markets = await poly.list_markets(limit=limit)
    finally:
        await poly.close()
    table = Table(title=f"Top {len(markets)} Polymarket markets")
    table.add_column("market_id", overflow="fold", max_width=20)
    table.add_column("question", overflow="fold")
    table.add_column("vol", justify="right")
    table.add_column("liq", justify="right")
    for m in markets[:limit]:
        table.add_row(m.market_id[:18], m.question[:80], f"{m.volume:,.0f}", f"{m.liquidity:,.0f}")
    console.print(table)


async def cmd_news() -> None:
    items = await fetch_rss_all()
    for n in items[:20]:
        console.print(f"[dim]{n.published:%Y-%m-%d %H:%M}[/dim] [bold]{n.source[:30]}[/bold] {n.title}")


async def cmd_run(*, limit: int, dry_run: bool) -> None:
    state = PortfolioState.load(STATE_PATH, settings.paper_bankroll)
    poly = PolymarketClient()
    try:
        log.info("loop_start", bankroll=state.cash, mode=settings.trading_mode)
        markets = await poly.list_markets(limit=limit)
        if not markets:
            log.warning("no_markets")
            return

        # Build candidate set with current prices
        candidates: list[dict] = []
        for m in markets:
            try:
                q = await poly.get_quote(m.market_id, "Yes")
                candidates.append(
                    {
                        "market_id": m.market_id,
                        "question": m.question,
                        "yes_price": q.yes_price,
                        "end_date": m.end_date.isoformat() if m.end_date else None,
                        "volume": m.volume,
                    }
                )
            except Exception as e:
                log.warning("quote_failed", market=m.market_id, err=str(e))

        news = await fetch_rss_all()
        news_titles = [n.title for n in news]
        news_dicts = [asdict(n) | {"published": n.published.isoformat()} for n in news]

        if not settings.anthropic_api_key:
            log.warning("no_anthropic_key_skipping_llm")
            return

        # Stage 1: Haiku screen
        short_ids = await screen_markets(candidates, news_titles)
        log.info("screened", n=len(short_ids), ids=short_ids)
        shortlisted = [c for c in candidates if c["market_id"] in short_ids][:5]
        if not shortlisted:
            log.info("nothing_shortlisted")
            return

        # Stage 2: Opus decide on each
        broker = PaperBroker(state, STATE_PATH)
        for m in shortlisted:
            d = await decide(m, news_dicts)
            log.info(
                "decision",
                market=m["market_id"][:10],
                est=round(d.estimated_prob, 3),
                mkt=round(d.market_prob, 3),
                edge=round(d.edge, 3),
                conf=round(d.confidence, 2),
                side=d.side,
            )
            if d.side == "PASS":
                continue
            equity = state.equity({c["market_id"]: c["yes_price"] for c in candidates})
            exposure_pct = state.exposure() / max(equity, 1e-6)
            notional = position_size_usd(
                estimated_prob=d.estimated_prob if d.side == "BUY_YES" else (1 - d.estimated_prob),
                market_price=m["yes_price"] if d.side == "BUY_YES" else (1 - m["yes_price"]),
                bankroll=equity,
                confidence=d.confidence,
                current_exposure_pct=exposure_pct,
            )
            log.info("size", market=m["market_id"][:10], notional=round(notional, 2))
            if notional < 1.0:
                continue
            if dry_run:
                log.info("dry_run_skip_fill")
                continue
            broker.execute(
                market_id=m["market_id"],
                side="YES" if d.side == "BUY_YES" else "NO",
                notional_usd=notional,
                yes_price=m["yes_price"],
            )

        equity = state.equity({c["market_id"]: c["yes_price"] for c in candidates})
        log.info(
            "loop_end",
            cash=round(state.cash, 2),
            positions=len(state.positions),
            equity=round(equity, 2),
        )
    finally:
        await poly.close()


async def cmd_status() -> None:
    state = PortfolioState.load(STATE_PATH, settings.paper_bankroll)
    poly = PolymarketClient()
    try:
        prices: dict[str, float] = {}
        for mid in state.positions:
            try:
                q = await poly.get_quote(mid, "Yes")
                prices[mid] = q.yes_price
            except Exception:
                prices[mid] = state.positions[mid].avg_price
    finally:
        await poly.close()

    table = Table(title="Paper portfolio")
    table.add_column("market")
    table.add_column("side")
    table.add_column("shares", justify="right")
    table.add_column("avg", justify="right")
    table.add_column("now", justify="right")
    table.add_column("mtm", justify="right")
    table.add_column("pnl", justify="right")
    for mid, p in state.positions.items():
        cur = prices.get(mid, p.avg_price)
        mtm = p.mark_to_market(cur)
        pnl = mtm - p.cost_basis
        table.add_row(mid[:14], p.side, f"{p.shares:.1f}", f"{p.avg_price:.3f}",
                      f"{cur if p.side=='YES' else 1-cur:.3f}", f"{mtm:.2f}", f"{pnl:+.2f}")
    console.print(table)
    console.print(f"Cash: ${state.cash:,.2f}  Equity: ${state.equity(prices):,.2f}  Fills: {len(state.fills)}")


def cli() -> None:
    configure_logging()
    p = argparse.ArgumentParser(prog="trader")
    sub = p.add_subparsers(dest="cmd", required=True)

    pm = sub.add_parser("markets", help="List top Polymarket markets")
    pm.add_argument("--limit", type=int, default=20)

    sub.add_parser("news", help="Fetch RSS news")

    pr = sub.add_parser("run", help="Run one analysis+execution loop")
    pr.add_argument("--limit", type=int, default=30)
    pr.add_argument("--dry-run", action="store_true")

    sub.add_parser("status", help="Show paper portfolio")

    args = p.parse_args()
    if args.cmd == "markets":
        asyncio.run(cmd_markets(args.limit))
    elif args.cmd == "news":
        asyncio.run(cmd_news())
    elif args.cmd == "run":
        asyncio.run(cmd_run(limit=args.limit, dry_run=args.dry_run))
    elif args.cmd == "status":
        asyncio.run(cmd_status())


if __name__ == "__main__":
    cli()
