# Trading Platform (MVP)

LLM-driven prediction-market trading platform. **Polymarket** first, paper trading only.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # fill in ANTHROPIC_API_KEY

trader markets --limit 20      # list top Polymarket markets
trader news                    # fetch RSS headlines
trader run --dry-run           # full pipeline, no fills
trader run                     # paper-trade one loop
trader status                  # show paper portfolio
```

## Architecture

```
src/trading/
  config.py              # pydantic settings from .env
  logging_setup.py       # structlog
  exchanges/
    base.py              # Exchange/Market/Quote interfaces
    polymarket.py        # Gamma + CLOB read-only client
  data/news.py           # RSS ingestion (feedparser)
  analysis/llm.py        # Haiku screener + Opus decider (JSON-mode)
  risk/kelly.py          # fractional Kelly + caps
  execution/paper.py     # in-memory paper broker
  portfolio/tracker.py   # positions, fills, mark-to-market, JSON persistence
  main.py                # CLI: markets|news|run|status
```

Loop: `list_markets → quotes → fetch_rss → Haiku screen → Opus decide → Kelly size → paper fill → save state`.

## Configuration

See `.env.example`. Important knobs:

- `KELLY_FRACTION=0.25` — quarter Kelly is conservative; full Kelly is aggressive.
- `MAX_POSITION_PCT=0.10` — hard cap per trade.
- `MAX_PORTFOLIO_EXPOSURE=0.80` — keep cash buffer.
- `MIN_EDGE=0.03` — only trade when |est_prob − market_price| ≥ 3%.

## Roadmap

1. Live Polymarket CLOB orders (py-clob-client integration).
2. Reddit / Twitter / web search ingestion.
3. WebSocket order book + slippage model.
4. Kalshi connector.
5. Backtesting harness on historical resolutions.
6. Position management (exits, stop-losses, time decay).
