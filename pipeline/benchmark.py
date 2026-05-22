"""CSI 300 / CSI 500 returns since March 1 of the report year.

Reads cached closes from data/benchmarks.json. If a needed date is missing
and TUSHARE_TOKEN is set, calls Tushare's index_daily endpoint to refresh.

Baseline = close on the last trading day strictly before March 1.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Optional

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "benchmarks.json"

INDEX_CODES = {
    "CSI300": "000300.SH",  # 沪深300
    "CSI500": "000905.SH",  # 中证500
}


@dataclass
class BenchmarkReturn:
    name: str            # display name, e.g. "沪深300"
    code: str            # ts_code
    baseline_date: str   # YYYY-MM-DD
    baseline_close: float
    end_date: str
    end_close: float
    return_pct: float    # percent, e.g. -1.57


DISPLAY_NAMES = {"CSI300": "沪深300", "CSI500": "中证500"}


def _load() -> dict:
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    return {code: {} for code in INDEX_CODES.values()}


def _save(cache: dict) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2,
                                    sort_keys=True), encoding="utf-8")


def _yyyymmdd(d: str) -> str:
    return d.replace("-", "")


def _fetch_from_tushare(ts_code: str, start: str, end: str) -> dict[str, float]:
    import requests
    token = os.environ["TUSHARE_TOKEN"]
    body = {
        "api_name": "index_daily",
        "token": token,
        "params": {"ts_code": ts_code, "start_date": start, "end_date": end},
        "fields": "trade_date,close",
    }
    r = requests.post("https://api.tushare.pro", json=body, timeout=30)
    r.raise_for_status()
    payload = r.json()
    if payload.get("code") != 0:
        raise RuntimeError(f"Tushare error: {payload.get('msg')}")
    fields = payload["data"]["fields"]
    di = fields.index("trade_date")
    ci = fields.index("close")
    return {row[di]: float(row[ci]) for row in payload["data"]["items"]}


def _ensure_dates(cache: dict, ts_code: str, year: int) -> dict[str, float]:
    needed_start = f"{year}0220"
    needed_end = f"{year}1231"
    series = cache.setdefault(ts_code, {})
    have_in_range = [d for d in series if needed_start <= d <= needed_end]
    if not have_in_range and os.environ.get("TUSHARE_TOKEN"):
        fresh = _fetch_from_tushare(ts_code, needed_start, needed_end)
        series.update(fresh)
        _save(cache)
    return series


def _last_close_before(series: dict[str, float], cutoff_yyyymmdd: str) -> tuple[str, float]:
    candidates = sorted(d for d in series if d < cutoff_yyyymmdd)
    if not candidates:
        raise RuntimeError(f"No cached close before {cutoff_yyyymmdd}; "
                           "set TUSHARE_TOKEN to refresh or extend data/benchmarks.json.")
    d = candidates[-1]
    return d, series[d]


def _close_on(series: dict[str, float], day_yyyymmdd: str) -> float:
    if day_yyyymmdd in series:
        return series[day_yyyymmdd]
    raise RuntimeError(f"No cached close for {day_yyyymmdd}; "
                       "set TUSHARE_TOKEN to refresh or extend data/benchmarks.json.")


def returns_since_march_first(end_date: str) -> list[BenchmarkReturn]:
    """end_date: 'YYYY-MM-DD'. Returns CSI 300 then CSI 500."""
    end_yyyymmdd = _yyyymmdd(end_date)
    year = int(end_date[:4])
    march_first = f"{year}0301"

    cache = _load()
    out: list[BenchmarkReturn] = []
    for key in ("CSI300", "CSI500"):
        ts_code = INDEX_CODES[key]
        series = _ensure_dates(cache, ts_code, year)
        bd, bc = _last_close_before(series, march_first)
        ec = _close_on(series, end_yyyymmdd)
        out.append(BenchmarkReturn(
            name=DISPLAY_NAMES[key],
            code=ts_code,
            baseline_date=f"{bd[:4]}-{bd[4:6]}-{bd[6:]}",
            baseline_close=bc,
            end_date=end_date,
            end_close=ec,
            return_pct=(ec - bc) / bc * 100.0,
        ))
    return out


if __name__ == "__main__":
    import sys
    for b in returns_since_march_first(sys.argv[1]):
        print(f"{b.name} ({b.code}): {b.return_pct:+.2f}% "
              f"({b.baseline_date} {b.baseline_close:.2f} -> {b.end_date} {b.end_close:.2f})")
