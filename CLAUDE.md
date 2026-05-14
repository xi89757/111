# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project does

A pipeline that turns a fund-NAV screenshot into a comparison table + chart:

1. Extract date, product names, unit NAVs, YTD returns, and daily NAV change from an
   uploaded image.
2. Pull CSI 300 (`000300.SH`) and CSI 500 (`000905.SH`) closes and compute their
   returns since March 1 of the screenshot's year (baseline = last trading day
   strictly before March 1).
3. Write a Markdown + CSV table, append a row to `data/records.csv`, and render a
   comparison chart (horizontal bar of YTD return per fund, with vertical dashed
   reference lines for the two benchmarks; a small secondary panel shows daily
   NAV change).

## Layout

```
pipeline/
  extractor.py   # image -> structured JSON (Claude vision; sidecar JSON fallback)
  benchmark.py   # CSI 300 / CSI 500 returns since March 1 (cached + Tushare refresh)
  report.py      # table (md/csv) + matplotlib chart
  run.py         # CLI: python -m pipeline.run <image>
  watch.py       # CLI: python -m pipeline.watch <folder>
data/
  benchmarks.json   # cached index closes keyed by ts_code -> YYYYMMDD -> close
  records.csv       # appended history (rows for the same date are replaced on re-run)
output/
  YYYYMMDD_table.md / .csv / _chart.png   # one set per processed image
samples/                                  # drop screenshots here
```

## Commands

```bash
pip install -r requirements.txt

# one-shot
python -m pipeline.run samples/20260410.png

# watch a folder; each new image is processed automatically
python -m pipeline.watch samples/

# refresh benchmark closes (otherwise falls back to data/benchmarks.json)
export TUSHARE_TOKEN=...

# vision extraction (otherwise expects a sidecar foo.json next to foo.png)
export ANTHROPIC_API_KEY=...
```

The sidecar-JSON fallback powered the first run (`samples/20260410.json`),
so neither API key is required to reproduce `output/20260410_*`.

## Conventions

- All percent values inside JSON, CSV, and matplotlib are stored as numbers
  WITHOUT the `%` sign (1.23 means 1.23%). Display formatting adds the sign.
- Benchmark baseline = close on the last trading day strictly before March 1
  (e.g. for 2026 that is 2026-02-27). Stated explicitly in every output label.
- `records.csv` is append-only across dates; re-running a date overwrites
  that date's rows in place.
