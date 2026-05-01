from trading.risk.kelly import kelly_fraction_binary, position_size_usd


def test_no_edge_returns_zero():
    assert kelly_fraction_binary(0.5, 0.5) == 0.0


def test_yes_side_edge():
    # p=0.6, q=0.5 => f* = 0.1 / 0.5 = 0.2
    assert abs(kelly_fraction_binary(0.6, 0.5) - 0.2) < 1e-9


def test_no_side_edge():
    # p=0.4, q=0.5 => f* = 0.1 / 0.5 = 0.2
    assert abs(kelly_fraction_binary(0.4, 0.5) - 0.2) < 1e-9


def test_position_size_respects_caps(monkeypatch):
    from trading import config as cfg
    monkeypatch.setattr(cfg.settings, "kelly_fraction", 1.0)
    monkeypatch.setattr(cfg.settings, "max_position_pct", 0.05)
    monkeypatch.setattr(cfg.settings, "max_portfolio_exposure", 0.80)
    n = position_size_usd(
        estimated_prob=0.8, market_price=0.5, bankroll=1000, confidence=1.0, current_exposure_pct=0.0
    )
    # Full Kelly would be (0.8-0.5)/0.5 = 0.6 -> capped at 0.05 -> $50
    assert abs(n - 50.0) < 1e-6
