from __future__ import annotations

import json
from dataclasses import dataclass

from anthropic import AsyncAnthropic

from ..config import settings
from ..logging_setup import get_logger

log = get_logger(__name__)

_client: AsyncAnthropic | None = None


def client() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


@dataclass
class Decision:
    market_id: str
    outcome: str
    estimated_prob: float
    market_prob: float
    edge: float
    confidence: float
    reasoning: str
    side: str  # BUY_YES | BUY_NO | PASS


async def screen_markets(markets: list[dict], news_titles: list[str]) -> list[str]:
    """Haiku pass: return market_ids worth deeper analysis."""
    if not markets:
        return []
    prompt = (
        "You screen prediction markets for trading opportunities. "
        "Return ONLY a JSON array of market_id strings that look most likely "
        "to be mispriced given recent news. Pick at most 5.\n\n"
        f"Recent news headlines:\n- " + "\n- ".join(news_titles[:30]) + "\n\n"
        f"Markets (id, question, current_yes_price):\n"
        + "\n".join(f"- {m['market_id']} | {m['question']} | yes={m['yes_price']:.2f}" for m in markets)
    )
    resp = await client().messages.create(
        model=settings.screener_model,
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    try:
        start = text.find("[")
        end = text.rfind("]")
        ids = json.loads(text[start : end + 1]) if start >= 0 else []
        return [str(x) for x in ids]
    except Exception as e:
        log.warning("screener_parse_failed", err=str(e), text=text[:200])
        return []


DECIDER_SYSTEM = """You are an expert prediction-market analyst.
Given a market question, the current market price, and relevant news,
estimate the TRUE probability of the YES outcome resolving true.
Be calibrated — only deviate from market price when you have a clear reason.
Return STRICT JSON only:
{"estimated_prob": float in [0,1], "confidence": float in [0,1], "reasoning": short string}
"""


async def decide(market: dict, news: list[dict]) -> Decision:
    news_block = "\n".join(f"- [{n['source']}] {n['title']}: {n['summary'][:200]}" for n in news[:15])
    user = (
        f"Market question: {market['question']}\n"
        f"Current YES price (market-implied prob): {market['yes_price']:.3f}\n"
        f"Resolves: {market.get('end_date', 'unknown')}\n\n"
        f"Recent news:\n{news_block or '(none)'}"
    )
    resp = await client().messages.create(
        model=settings.decider_model,
        max_tokens=1024,
        system=DECIDER_SYSTEM,
        messages=[{"role": "user", "content": user}],
    )
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    try:
        start = text.find("{")
        end = text.rfind("}")
        obj = json.loads(text[start : end + 1])
        est = float(obj["estimated_prob"])
        conf = float(obj.get("confidence", 0.5))
        reasoning = str(obj.get("reasoning", ""))[:500]
    except Exception as e:
        log.warning("decider_parse_failed", err=str(e), text=text[:200])
        est, conf, reasoning = market["yes_price"], 0.0, "parse_failed"

    market_p = market["yes_price"]
    edge = est - market_p
    if abs(edge) < settings.min_edge or conf < 0.4:
        side = "PASS"
    elif edge > 0:
        side = "BUY_YES"
    else:
        side = "BUY_NO"
    return Decision(
        market_id=market["market_id"],
        outcome="Yes",
        estimated_prob=est,
        market_prob=market_p,
        edge=edge,
        confidence=conf,
        reasoning=reasoning,
        side=side,
    )
