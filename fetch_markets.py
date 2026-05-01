#!/usr/bin/env python
"""Standalone market fetcher - no package imports."""
import asyncio
import json
from datetime import datetime, timezone

try:
    import httpx
    from tenacity import retry, stop_after_attempt, wait_exponential
    from rich.console import Console
    from rich.table import Table
except ImportError as e:
    print(f"Missing dependency: {e}")
    print("Run: pip install httpx tenacity feedparser rich")
    exit(1)


GAMMA_API = "https://gamma-api.polymarket.com"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
async def fetch_markets(limit: int = 10):
    """Fetch top markets from Polymarket Gamma API."""
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.get(
            f"{GAMMA_API}/markets",
            params={
                "limit": limit,
                "order": "volume24hr",
                "ascending": False,
                "active": "true",
                "closed": "false",
            }
        )
        r.raise_for_status()
        return r.json()


async def main():
    console = Console()
    try:
        console.print("[bold cyan]Fetching top 10 Polymarket markets...[/bold cyan]")
        data = await fetch_markets(limit=10)
        rows = data if isinstance(data, list) else data.get("data", [])

        if not rows:
            console.print("[red]No markets found[/red]")
            return

        table = Table(title=f"🔥 Top {len(rows[:10])} Polymarket Markets")
        table.add_column("Market ID", style="cyan", width=18)
        table.add_column("Question", overflow="fold", width=70)
        table.add_column("Vol 24h", justify="right", style="yellow")
        table.add_column("YES%", justify="right", style="green")

        for m in rows[:10]:
            try:
                market_id = str(m.get("conditionId") or m.get("id"))
                question = m.get("question", "")[:70]
                volume = m.get("volume", 0) or 0
                outcomes = m.get("outcomes")
                if isinstance(outcomes, str):
                    outcomes = json.loads(outcomes)
                prices = m.get("outcomePrices")
                if isinstance(prices, str):
                    prices = json.loads(prices)
                yes_price = float(prices[0]) if prices else 0.5

                vol_str = f"${volume/1e6:.1f}M" if volume > 1e6 else f"${volume/1e3:.0f}K"
                yes_pct = f"{yes_price*100:.1f}%"

                table.add_row(market_id[:16], question, vol_str, yes_pct)
            except Exception as e:
                console.print(f"[yellow]Error parsing market: {e}[/yellow]")

        console.print(table)
        console.print(f"\n[dim]✓ Fetched {len(rows[:10])} markets[/dim]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
