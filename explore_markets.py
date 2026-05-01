#!/usr/bin/env python
"""Quick script to fetch and display live Polymarket data."""
import asyncio
import sys
sys.path.insert(0, 'src')

from trading.exchanges.polymarket import PolymarketClient
from trading.data.news import fetch_rss_all
from rich.console import Console
from rich.table import Table

console = Console()


async def main():
    poly = PolymarketClient()
    try:
        console.print("[bold cyan]Fetching top 20 Polymarket markets...[/bold cyan]")
        markets = await poly.list_markets(limit=20)

        table = Table(title="🔥 Top Polymarket Markets", show_header=True)
        table.add_column("Market ID", style="cyan", width=18)
        table.add_column("Question", overflow="fold", width=60)
        table.add_column("Vol 24h", justify="right", style="yellow")
        table.add_column("YES%", justify="right", style="green")
        table.add_column("Liquidity", justify="right", style="blue")

        for m in markets[:20]:
            try:
                q = await poly.get_quote(m.market_id, "Yes")
                yes_pct = f"{q.yes_price*100:.1f}%"
            except Exception as e:
                yes_pct = "—"

            vol = f"${m.volume/1e6:.1f}M" if m.volume > 1e6 else f"${m.volume/1e3:.0f}K"
            liq = f"${m.liquidity/1e3:.0f}K"
            table.add_row(
                m.market_id[:16],
                m.question[:55],
                vol,
                yes_pct,
                liq,
            )
        console.print(table)
        console.print(f"\n[dim]Fetched {len(markets)} markets[/dim]")

        console.print("\n[bold cyan]Recent RSS news:[/bold cyan]")
        news = await fetch_rss_all()
        for n in news[:15]:
            console.print(f"[yellow]{n.published:%m-%d %H:%M}[/yellow] [{n.source[:20]}] {n.title[:70]}")
    finally:
        await poly.close()


if __name__ == "__main__":
    asyncio.run(main())
