"""Build the markdown/CSV table and the comparison chart.

Table columns: 产品 | 基金单位净值 | 今年以来收益率 | 单日单位净值变动
Plus two benchmark rows: 沪深300 / 中证500, "since March 1" return.

Chart: horizontal bar chart, YTD return per product, with vertical dashed
reference lines for the two benchmarks.
"""
from __future__ import annotations

import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

from .benchmark import BenchmarkReturn
from .extractor import Extraction


def _setup_chinese_font() -> None:
    candidates = [
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]
    for path in candidates:
        if Path(path).exists():
            font_manager.fontManager.addfont(path)
            family = font_manager.FontProperties(fname=path).get_name()
            plt.rcParams["font.sans-serif"] = [family]
            plt.rcParams["axes.unicode_minus"] = False
            return


def build_table(extraction: Extraction, benchmarks: list[BenchmarkReturn]) -> list[dict]:
    rows: list[dict] = []
    for p in extraction.products:
        rows.append({
            "type": "fund",
            "name": p.name,
            "nav": f"{p.nav:.4f}",
            "ytd_return_pct": f"{p.ytd_return_pct:+.2f}%",
            "daily_change_pct": f"{p.daily_change_pct:+.3f}%",
        })
    for b in benchmarks:
        rows.append({
            "type": "benchmark",
            "name": f"{b.name} (自{b.baseline_date}起)",
            "nav": "-",
            "ytd_return_pct": f"{b.return_pct:+.2f}%",
            "daily_change_pct": "-",
        })
    return rows


def write_markdown(rows: list[dict], out_path: Path, date: str) -> None:
    lines = [
        f"# 基金净值与基准对照表 ({date})",
        "",
        "| 名称 | 基金单位净值 | 今年以来收益率 | 单日单位净值变动 |",
        "| --- | ---: | ---: | ---: |",
    ]
    for r in rows:
        prefix = "**" if r["type"] == "benchmark" else ""
        lines.append(f"| {prefix}{r['name']}{prefix} | {r['nav']} | "
                     f"{r['ytd_return_pct']} | {r['daily_change_pct']} |")
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_csv(rows: list[dict], out_path: Path) -> None:
    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["type", "name", "nav",
                                          "ytd_return_pct", "daily_change_pct"])
        w.writeheader()
        w.writerows(rows)


def append_records(extraction: Extraction, benchmarks: list[BenchmarkReturn],
                   csv_path: Path) -> None:
    header = ["date", "kind", "name", "nav",
              "ytd_return_pct", "daily_change_pct"]
    existing: list[list[str]] = []
    if csv_path.exists():
        with csv_path.open("r", encoding="utf-8", newline="") as f:
            r = csv.reader(f)
            rows = list(r)
        if rows and rows[0] == header:
            existing = [row for row in rows[1:] if row and row[0] != extraction.date]

    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(existing)
        for p in extraction.products:
            w.writerow([extraction.date, "fund", p.name,
                        f"{p.nav:.4f}",
                        f"{p.ytd_return_pct:.4f}",
                        f"{p.daily_change_pct:.4f}"])
        for b in benchmarks:
            w.writerow([extraction.date, "benchmark",
                        f"{b.name}_since_{b.baseline_date}",
                        "",
                        f"{b.return_pct:.4f}",
                        ""])


def build_chart(extraction: Extraction, benchmarks: list[BenchmarkReturn],
                out_path: Path) -> None:
    _setup_chinese_font()

    names = [p.name for p in extraction.products]
    ytd = [p.ytd_return_pct for p in extraction.products]
    daily = [p.daily_change_pct for p in extraction.products]

    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(11, 7.5),
        gridspec_kw={"height_ratios": [3, 1.2], "hspace": 0.45},
    )

    colors = ["#2e8b57" if v >= 0 else "#c0392b" for v in ytd]
    bars = ax1.barh(names, ytd, color=colors, edgecolor="white")
    ax1.axvline(0, color="#888", linewidth=0.8)
    ax1.invert_yaxis()
    span = max(max(ytd, default=0), 0) - min(min(ytd, default=0), 0)
    pad = max(span * 0.12, 1.5)
    ax1.set_xlim(min(min(ytd, default=0), 0) - pad,
                 max(max(ytd, default=0), 0) + pad)

    bench_styles = [("--", "#1f6feb"), (":", "#d97706")]
    for b, (ls, color) in zip(benchmarks, bench_styles):
        label = f"{b.name} 自{b.baseline_date}起 ({b.return_pct:+.2f}%)"
        ax1.axvline(b.return_pct, linestyle=ls, color=color, linewidth=1.6, label=label)

    for bar, v in zip(bars, ytd):
        ax1.text(v + (0.3 if v >= 0 else -0.3), bar.get_y() + bar.get_height() / 2,
                 f"{v:+.2f}%", va="center",
                 ha="left" if v >= 0 else "right", fontsize=9)

    ax1.set_xlabel("今年以来收益率 (%)")
    ax1.set_title(f"基金今年以来收益率 vs. 基准 ({extraction.date})")
    ax1.legend(loc="lower right", fontsize=9)
    ax1.grid(axis="x", linestyle="--", alpha=0.35)

    daily_colors = ["#2e8b57" if v >= 0 else "#c0392b" for v in daily]
    ax2.bar(names, daily, color=daily_colors, edgecolor="white")
    ax2.axhline(0, color="#888", linewidth=0.8)
    ax2.set_ylabel("单日变动 (%)")
    ax2.set_title("单日单位净值变动")
    ax2.tick_params(axis="x", labelrotation=20)
    ax2.grid(axis="y", linestyle="--", alpha=0.35)

    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
