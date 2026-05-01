from __future__ import annotations

from ..config import settings


def kelly_fraction_binary(p: float, price: float) -> float:
    """Kelly stake fraction for a binary contract priced in [0,1].

    Buying YES at price q wins (1-q) per $1 staked with prob p, loses q with prob (1-p).
    Optimal full-Kelly fraction f* = (p*(1-q) - (1-p)*q) / ((1-q)*q) simplified to (p - q) / (1 - q) when betting one side?

    For a binary contract where we pay `q` and receive 1 if YES, the EV per $1 of contract is (p - q).
    With bankroll B, optimal fraction of bankroll to allocate (full Kelly) is:
        f* = (p - q) / (1 - q)   if buying YES (p > q)
        f* = (q - p) / q         if buying NO  (p < q)
    Returns 0.0 if no edge.
    """
    p = max(0.0, min(1.0, p))
    q = max(1e-6, min(1 - 1e-6, price))
    if p > q:
        return max(0.0, (p - q) / (1.0 - q))
    if p < q:
        return max(0.0, (q - p) / q)
    return 0.0


def position_size_usd(
    *,
    estimated_prob: float,
    market_price: float,
    bankroll: float,
    confidence: float = 1.0,
    current_exposure_pct: float = 0.0,
) -> float:
    """Return USD notional to allocate, after fractional-Kelly + risk caps."""
    f_full = kelly_fraction_binary(estimated_prob, market_price)
    f = f_full * settings.kelly_fraction * max(0.0, min(1.0, confidence))
    f = min(f, settings.max_position_pct)
    headroom = max(0.0, settings.max_portfolio_exposure - current_exposure_pct)
    f = min(f, headroom)
    return max(0.0, bankroll * f)
