"""Combined multi-day report.

Reads per-day extractions (from samples/<YYYYMMDD>.json sidecars) and produces:
  - <stem>_table.md    NAV grid (rows = products, cols = dates) + YTD grid
  - <stem>_table.csv   long format: (date, product, nav, ytd_return_pct,
                       daily_change_pct)
  - <stem>_chart.png   line chart of YTD% across days, with CSI 300 / CSI 500
                       since-March-1 trajectories overlaid

Usage:
    python -m pipeline.combined 20260413 20260414 20260415 20260416 20260417
    python -m pipeline.combined --range 2026-04-13 2026-04-17
    python -m pipeline.combined --samples-dir samples 20260413 ...
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import date, timedelta
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .benchmark import returns_since_march_first, BenchmarkReturn
from .extractor import Extraction, _from_dict
from .report import _setup_chinese_font


def _load_sidecar(samples_dir: Path, yyyymmdd: str) -> Extraction:
    path = samples_dir / f"{yyyymmdd}.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found; run pipeline.run first to extract it.")
    return _from_dict(json.loads(path.read_text(encoding="utf-8")))


def _iso(yyyymmdd: str) -> str:
    return f"{yyyymmdd[:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:]}"


def _stem(yyyymmdds: list[str]) -> str:
    return f"{yyyymmdds[0]}_{yyyymmdds[-1]}"


def _all_product_names(extractions: list[Extraction]) -> list[str]:
    seen: list[str] = []
    for e in extractions:
        for p in e.products:
            if p.name not in seen:
                seen.append(p.name)
    return seen


def _nav_grid(extractions: list[Extraction], product_order: list[str]) -> dict[str, dict[str, float | None]]:
    grid: dict[str, dict[str, float | None]] = {name: {} for name in product_order}
    for e in extractions:
        by_name = {p.name: p for p in e.products}
        for name in product_order:
            p = by_name.get(name)
            grid[name][e.date] = p.nav if p else None
    return grid


def _ytd_grid(extractions: list[Extraction], product_order: list[str]) -> dict[str, dict[str, float | None]]:
    grid: dict[str, dict[str, float | None]] = {name: {} for name in product_order}
    for e in extractions:
        by_name = {p.name: p for p in e.products}
        for name in product_order:
            p = by_name.get(name)
            grid[name][e.date] = p.ytd_return_pct if p else None
    return grid


def _write_markdown(out_path: Path, extractions: list[Extraction],
                    bench_by_date: dict[str, list[BenchmarkReturn]],
                    product_order: list[str]) -> None:
    dates = [e.date for e in extractions]
    nav = _nav_grid(extractions, product_order)
    ytd = _ytd_grid(extractions, product_order)

    lines = [f"# 基金净值多日对照 ({dates[0]} ~ {dates[-1]})", ""]
    lines.append("## 基金单位净值")
    lines.append("| 产品 | " + " | ".join(dates) + " |")
    lines.append("| --- | " + " | ".join(["---:"] * len(dates)) + " |")
    for name in product_order:
        cells = [f"{nav[name][d]:.4f}" if nav[name].get(d) is not None else "-" for d in dates]
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    lines.append("")
    lines.append("## 今年以来收益率")
    lines.append("| 名称 | " + " | ".join(dates) + " |")
    lines.append("| --- | " + " | ".join(["---:"] * len(dates)) + " |")
    for name in product_order:
        cells = [f"{ytd[name][d]:+.2f}%" if ytd[name].get(d) is not None else "-" for d in dates]
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    bench300 = [bench_by_date[d][0].return_pct for d in dates]
    bench500 = [bench_by_date[d][1].return_pct for d in dates]
    baseline_date = bench_by_date[dates[0]][0].baseline_date
    lines.append(f"| **沪深300 (自{baseline_date}起)** | "
                 + " | ".join(f"{v:+.2f}%" for v in bench300) + " |")
    lines.append(f"| **中证500 (自{baseline_date}起)** | "
                 + " | ".join(f"{v:+.2f}%" for v in bench500) + " |")
    lines.append("")
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_csv(out_path: Path, extractions: list[Extraction],
               bench_by_date: dict[str, list[BenchmarkReturn]]) -> None:
    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "kind", "name", "nav",
                    "ytd_return_pct", "daily_change_pct"])
        for e in extractions:
            for p in e.products:
                w.writerow([e.date, "fund", p.name,
                            f"{p.nav:.4f}",
                            f"{p.ytd_return_pct:.4f}",
                            f"{p.daily_change_pct:.4f}"])
        for d, benches in bench_by_date.items():
            for b in benches:
                w.writerow([d, "benchmark",
                            f"{b.name}_since_{b.baseline_date}",
                            "", f"{b.return_pct:.4f}", ""])


def _build_chart(out_path: Path, extractions: list[Extraction],
                 bench_by_date: dict[str, list[BenchmarkReturn]],
                 product_order: list[str]) -> None:
    _setup_chinese_font()

    dates = [e.date for e in extractions]
    short_labels = [d[5:] for d in dates]  # MM-DD
    ytd_grid = _ytd_grid(extractions, product_order)

    fig, ax = plt.subplots(figsize=(11, 6.5))

    cmap = plt.get_cmap("tab10")
    for i, name in enumerate(product_order):
        ys = [ytd_grid[name].get(d) for d in dates]
        ax.plot(short_labels, ys, marker="o", linewidth=1.6,
                color=cmap(i % 10), label=name)

    bench300 = [bench_by_date[d][0].return_pct for d in dates]
    bench500 = [bench_by_date[d][1].return_pct for d in dates]
    baseline_date = bench_by_date[dates[0]][0].baseline_date
    ax.plot(short_labels, bench300, linestyle="--", marker="s",
            linewidth=2.2, color="#1f6feb",
            label=f"沪深300 (自{baseline_date}起)")
    ax.plot(short_labels, bench500, linestyle=":", marker="^",
            linewidth=2.2, color="#d97706",
            label=f"中证500 (自{baseline_date}起)")

    ax.axhline(0, color="#888", linewidth=0.8)
    ax.set_ylabel("今年以来收益率 (%)")
    ax.set_xlabel("日期")
    ax.set_title(f"基金 vs. 基准 — 今年以来收益率走势 ({dates[0]} ~ {dates[-1]})")
    ax.grid(axis="y", linestyle="--", alpha=0.35)
    ax.legend(loc="center left", bbox_to_anchor=(1.01, 0.5), fontsize=9, frameon=False)

    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Multi-day combined report.")
    ap.add_argument("dates", nargs="*", help="YYYYMMDD list")
    ap.add_argument("--range", nargs=2, metavar=("START", "END"),
                    help="ISO date range, e.g. 2026-04-13 2026-04-17 (inclusive)")
    ap.add_argument("--samples-dir", type=Path, default=Path("samples"))
    ap.add_argument("--out-dir", type=Path, default=Path("output"))
    args = ap.parse_args(argv)

    if args.range:
        start = date.fromisoformat(args.range[0])
        end = date.fromisoformat(args.range[1])
        if end < start:
            raise SystemExit("range end is before start")
        yyyymmdds: list[str] = []
        cur = start
        while cur <= end:
            ymd = cur.strftime("%Y%m%d")
            if (args.samples_dir / f"{ymd}.json").exists():
                yyyymmdds.append(ymd)
            cur += timedelta(days=1)
    else:
        yyyymmdds = sorted(args.dates)

    if not yyyymmdds:
        raise SystemExit("no dates resolved; pass YYYYMMDD args or --range")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    extractions = [_load_sidecar(args.samples_dir, d) for d in yyyymmdds]
    bench_by_date = {e.date: returns_since_march_first(e.date) for e in extractions}
    product_order = _all_product_names(extractions)

    stem = _stem(yyyymmdds)
    md_path = args.out_dir / f"{stem}_table.md"
    csv_path = args.out_dir / f"{stem}_table.csv"
    chart_path = args.out_dir / f"{stem}_chart.png"

    _write_markdown(md_path, extractions, bench_by_date, product_order)
    _write_csv(csv_path, extractions, bench_by_date)
    _build_chart(chart_path, extractions, bench_by_date, product_order)

    print(json.dumps({
        "dates": [e.date for e in extractions],
        "products": product_order,
        "outputs": [str(md_path), str(csv_path), str(chart_path)],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
