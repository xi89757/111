"""End-to-end CLI.

Usage:
    python -m pipeline.run path/to/screenshot.png
    python -m pipeline.run path/to/screenshot.png --out-dir output --data-dir data

Outputs (named by the image's date, e.g. 20260410):
    <out>/<YYYYMMDD>_table.md
    <out>/<YYYYMMDD>_table.csv
    <out>/<YYYYMMDD>_chart.png
And appends each run's rows to <data>/records.csv.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .extractor import extract
from .benchmark import returns_since_march_first
from .report import (append_records, build_chart, build_table, write_csv,
                     write_markdown)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Fund-NAV screenshot -> table + chart.")
    ap.add_argument("image", type=Path)
    ap.add_argument("--out-dir", type=Path, default=Path("output"))
    ap.add_argument("--data-dir", type=Path, default=Path("data"))
    args = ap.parse_args(argv)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    args.data_dir.mkdir(parents=True, exist_ok=True)

    extraction = extract(args.image)
    benchmarks = returns_since_march_first(extraction.date)

    stem = extraction.date.replace("-", "")
    rows = build_table(extraction, benchmarks)
    write_markdown(rows, args.out_dir / f"{stem}_table.md", extraction.date)
    write_csv(rows, args.out_dir / f"{stem}_table.csv")
    build_chart(extraction, benchmarks, args.out_dir / f"{stem}_chart.png")
    append_records(extraction, benchmarks, args.data_dir / "records.csv")

    print(json.dumps({
        "date": extraction.date,
        "products": len(extraction.products),
        "benchmarks": [{"name": b.name, "return_pct": round(b.return_pct, 2)}
                       for b in benchmarks],
        "outputs": [
            str(args.out_dir / f"{stem}_table.md"),
            str(args.out_dir / f"{stem}_table.csv"),
            str(args.out_dir / f"{stem}_chart.png"),
        ],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
