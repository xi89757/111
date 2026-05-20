"""Combined multi-day report.

Reads per-day extractions (from samples/<YYYYMMDD>.json sidecars) and produces:
  - <stem>_table.md    NAV grid (rows = products, cols = dates) + YTD grid
  - <stem>_table.csv   long format: (date, product, nav, ytd_return_pct,
                       daily_change_pct)
  - <stem>_table.xlsx  one sheet per product (rows = metrics, cols = dates);
                       领航1号's sheet additionally carries CSI 300 / CSI 500
                       closes, a live cumulative-excess formula, and the
                       embedded comparison chart
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

from .benchmark import returns_since_march_first, BenchmarkReturn, _load as _load_bench_cache, INDEX_CODES, DISPLAY_NAMES
from .extractor import Extraction, _from_dict
from .report import _setup_chinese_font


def _bench_daily_pct(dates_iso: list[str]) -> dict[str, dict[str, float]]:
    """For each ISO date in `dates_iso`, return daily % change for CSI 300 and
    CSI 500 vs the previous cached trading day."""
    cache = _load_bench_cache()
    out: dict[str, dict[str, float]] = {"CSI300": {}, "CSI500": {}}
    for key in ("CSI300", "CSI500"):
        series = cache.get(INDEX_CODES[key], {})
        sorted_days = sorted(series.keys())
        for d_iso in dates_iso:
            d = d_iso.replace("-", "")
            if d not in series:
                continue
            idx = sorted_days.index(d)
            if idx == 0:
                continue
            prev = sorted_days[idx - 1]
            pct = (series[d] - series[prev]) / series[prev] * 100.0
            out[key][d_iso] = pct
    return out


def _bench_close(dates_iso: list[str]) -> dict[str, dict[str, float]]:
    """For each ISO date, the raw closing index point for CSI 300 / CSI 500."""
    cache = _load_bench_cache()
    out: dict[str, dict[str, float]] = {"CSI300": {}, "CSI500": {}}
    for key in ("CSI300", "CSI500"):
        series = cache.get(INDEX_CODES[key], {})
        for d_iso in dates_iso:
            d = d_iso.replace("-", "")
            if d in series:
                out[key][d_iso] = series[d]
    return out


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


def _write_xlsx(out_path: Path, extractions: list[Extraction],
                bench_by_date: dict[str, list[BenchmarkReturn]],
                product_order: list[str],
                lh_chart_path: Path | None = None) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
    from openpyxl.utils import get_column_letter
    from openpyxl.drawing.image import Image as XLImage

    dates = [e.date for e in extractions]
    nav = _nav_grid(extractions, product_order)
    ytd = _ytd_grid(extractions, product_order)
    daily: dict[str, dict[str, float | None]] = {n: {} for n in product_order}
    for e in extractions:
        by_name = {p.name: p for p in e.products}
        for n in product_order:
            p = by_name.get(n)
            daily[n][e.date] = p.daily_change_pct if p else None

    bench_close = _bench_close(dates)

    wb = Workbook()
    wb.remove(wb.active)

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="305496")
    bench_font = Font(bold=True, italic=True)
    bench_fill = PatternFill("solid", fgColor="FFF2CC")
    excess_font = Font(bold=True, color="9C0006")
    excess_fill = PatternFill("solid", fgColor="FCE4D6")
    thin = Side(style="thin", color="BFBFBF")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    center = Alignment(horizontal="center", vertical="center")
    right = Alignment(horizontal="right", vertical="center")

    def _header(ws, label_col_title: str) -> None:
        c = ws.cell(row=1, column=1, value=label_col_title)
        c.font = header_font
        c.fill = header_fill
        c.alignment = center
        c.border = border
        for j, d in enumerate(dates, start=2):
            c = ws.cell(row=1, column=j, value=d)
            c.font = header_font
            c.fill = header_fill
            c.alignment = center
            c.border = border

    def _metric_row(ws, row: int, label: str,
                    values: dict[str, float | None], number_fmt: str,
                    *, divide_by_100: bool = False,
                    fill: PatternFill | None = None,
                    label_font: Font | None = None) -> None:
        nc = ws.cell(row=row, column=1, value=label)
        nc.font = label_font or Font(bold=True)
        if fill is not None:
            nc.fill = fill
        nc.alignment = center
        nc.border = border
        for j, d in enumerate(dates, start=2):
            v = values.get(d)
            if v is not None and divide_by_100:
                v = v / 100.0
            c = ws.cell(row=row, column=j, value=v)
            c.number_format = number_fmt
            if fill is not None:
                c.fill = fill
            c.alignment = right
            c.border = border

    def _finalize(ws) -> None:
        ws.column_dimensions["A"].width = 28
        for j in range(2, 2 + len(dates)):
            ws.column_dimensions[get_column_letter(j)].width = 12
        ws.freeze_panes = "B2"

    for name in product_order:
        ws = wb.create_sheet(name)
        _header(ws, name)

        _metric_row(ws, 2, "基金单位净值", nav[name], "0.0000")
        _metric_row(ws, 3, "今年以来收益率", ytd[name], "0.00%",
                    divide_by_100=True)
        _metric_row(ws, 4, "单日单位净值变动", daily[name], "0.000%",
                    divide_by_100=True)

        if name == "领航1号":
            _metric_row(ws, 5, "沪深300 (收盘点位)", bench_close["CSI300"],
                        "0.00", fill=bench_fill, label_font=bench_font)
            _metric_row(ws, 6, "中证500 (收盘点位)", bench_close["CSI500"],
                        "0.00", fill=bench_fill, label_font=bench_font)

            lh_row, cs_row, cum_row = 2, 6, 7
            nc = ws.cell(row=cum_row, column=1,
                         value="领航1号 - 中证500 累计超额")
            nc.font = excess_font
            nc.fill = excess_fill
            nc.alignment = center
            nc.border = border
            b = get_column_letter(2)
            for j, d in enumerate(dates, start=2):
                col = get_column_letter(j)
                f = (f"=({col}{lh_row}/${b}${lh_row}-1)"
                     f"-({col}{cs_row}/${b}${cs_row}-1)")
                c = ws.cell(row=cum_row, column=j, value=f)
                c.number_format = "0.00%"
                c.fill = excess_fill
                c.alignment = right
                c.border = border

            formula_text = ("累计超额 = (领航1号净值 ÷ 首日净值 − 1) "
                            "− (中证500收盘 ÷ 首日收盘 − 1)；首日 = 0，单位：百分点")
            cap = ws.cell(row=cum_row + 2, column=1, value=formula_text)
            cap.font = Font(italic=True, color="9C0006")
            ws.merge_cells(start_row=cum_row + 2, start_column=1,
                           end_row=cum_row + 2,
                           end_column=min(2 + len(dates), 12))

            if lh_chart_path is not None and Path(lh_chart_path).exists():
                ws.add_image(XLImage(str(lh_chart_path)),
                             f"A{cum_row + 4}")

        _finalize(ws)

    wb.save(out_path)


def _build_daily_chart(out_path: Path, extractions: list[Extraction],
                       product_order: list[str]) -> None:
    """Daily % change: every product + CSI 300 + CSI 500 + 领航1号 excess."""
    _setup_chinese_font()

    dates = [e.date for e in extractions]
    n = len(dates)
    xs = list(range(n))
    short_labels = [d[5:] for d in dates]

    daily: dict[str, dict[str, float | None]] = {nm: {} for nm in product_order}
    for e in extractions:
        by_name = {p.name: p for p in e.products}
        for nm in product_order:
            p = by_name.get(nm)
            daily[nm][e.date] = p.daily_change_pct if p else None
    bench_daily = _bench_daily_pct(dates)

    width = max(11, 9 + n * 0.35)
    fig, ax = plt.subplots(figsize=(width, 6.5))
    marker_size = max(3, 7 - n // 8)
    cmap = plt.get_cmap("tab10")

    for i, name in enumerate(product_order):
        ys = [daily[name].get(d) for d in dates]
        ax.plot(xs, ys, marker="o", markersize=marker_size, linewidth=1.4,
                alpha=0.85, color=cmap(i % 10), label=name)

    ax.plot(xs, [bench_daily["CSI300"].get(d) for d in dates],
            linestyle="--", marker="s", markersize=marker_size,
            linewidth=2.2, color="#1f6feb", label="沪深300 (单日)")
    ax.plot(xs, [bench_daily["CSI500"].get(d) for d in dates],
            linestyle=":", marker="^", markersize=marker_size,
            linewidth=2.2, color="#d97706", label="中证500 (单日)")

    rj = daily.get("领航1号", {})
    excess = [
        (rj.get(d) - bench_daily["CSI500"].get(d))
        if (rj.get(d) is not None and bench_daily["CSI500"].get(d) is not None)
        else None
        for d in dates
    ]
    ax.plot(xs, excess, linestyle="-", marker="D", markersize=marker_size + 1,
            linewidth=2.4, color="#9C0006",
            label="领航1号 - 中证500 超额")

    ax.set_xticks(xs)
    ax.set_xticklabels(short_labels, rotation=45, ha="right",
                       fontsize=max(7, 9 - n // 10))
    ax.axhline(0, color="#888", linewidth=0.8)
    ax.set_ylabel("单日变动 (%)")
    ax.set_xlabel("日期")
    ax.set_title(f"单日变动 — 基金 / 基准 / 超额 ({dates[0]} ~ {dates[-1]})")
    ax.grid(axis="y", linestyle="--", alpha=0.35)
    ax.legend(loc="center left", bbox_to_anchor=(1.01, 0.5),
              fontsize=9, frameon=False)

    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def _build_lh_chart(out_path: Path, extractions: list[Extraction],
                    product_order: list[str]) -> None:
    """领航1号 only: unit NAV on the left axis, 领航1号 - 中证500 累计超额
    on the right axis. Rendered as a PNG so it displays in every viewer."""
    _setup_chinese_font()

    dates = [e.date for e in extractions]
    n = len(dates)
    xs = list(range(n))
    short_labels = [d[5:] for d in dates]

    nav = _nav_grid(extractions, product_order)
    bench_close = _bench_close(dates)
    lh = nav.get("领航1号", {})
    lh0 = lh.get(dates[0])
    cs0 = bench_close["CSI500"].get(dates[0])

    nav_y = [lh.get(d) for d in dates]
    excess_y = []
    for d in dates:
        lhd, csd = lh.get(d), bench_close["CSI500"].get(d)
        if None not in (lhd, lh0, csd, cs0) and lh0 and cs0:
            excess_y.append(((lhd / lh0 - 1) - (csd / cs0 - 1)) * 100.0)
        else:
            excess_y.append(None)

    width = max(11, 9 + n * 0.42)
    fig, ax = plt.subplots(figsize=(width, 6.2))
    ms = max(3, 7 - n // 8)

    l1, = ax.plot(xs, nav_y, marker="o", markersize=ms, linewidth=2.0,
                  color="#1F6FEB", label="领航1号 单位净值")
    ax.set_ylabel("领航1号 单位净值", color="#1F6FEB")
    ax.tick_params(axis="y", labelcolor="#1F6FEB")
    ax.set_xlabel("日期")
    ax.set_xticks(xs)
    ax.set_xticklabels(short_labels, rotation=45, ha="right",
                       fontsize=max(7, 9 - n // 10))
    ax.grid(axis="y", linestyle="--", alpha=0.3)

    ax2 = ax.twinx()
    l2, = ax2.plot(xs, excess_y, marker="D", markersize=ms + 1, linewidth=2.4,
                   color="#9C0006",
                   label="领航1号 - 中证500 累计超额 (右轴)")
    ax2.axhline(0, color="#9C0006", linewidth=0.6, alpha=0.4)
    ax2.set_ylabel("领航1号 - 中证500 累计超额 (百分点)", color="#9C0006")
    ax2.tick_params(axis="y", labelcolor="#9C0006")

    ax.set_title(f"领航1号 单位净值 与 累计超额 ({dates[0]} ~ {dates[-1]})")
    ax.legend(handles=[l1, l2], loc="upper left", fontsize=9, frameon=False)

    fig.text(0.5, -0.02,
             "累计超额 = (领航1号净值 ÷ 首日净值 − 1) "
             "− (中证500收盘 ÷ 首日收盘 − 1)；首日 = 0，单位：百分点",
             ha="center", fontsize=9, style="italic", color="#9C0006")

    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def _build_nav_chart(out_path: Path, extractions: list[Extraction],
                     product_order: list[str]) -> None:
    """Linear fluctuation chart for the NAV sheet. Funds and index points
    differ by ~4 orders of magnitude, so everything is rebased to 100 at the
    first date (cumulative-growth index). The 领航1号 - 中证500 cumulative
    excess (percentage points) rides a secondary axis."""
    _setup_chinese_font()

    dates = [e.date for e in extractions]
    n = len(dates)
    xs = list(range(n))
    short_labels = [d[5:] for d in dates]

    nav = _nav_grid(extractions, product_order)
    bench_close = _bench_close(dates)

    def _rebased(series: dict[str, float | None]) -> list[float | None]:
        base = series.get(dates[0])
        if not base:
            return [None] * n
        return [(series.get(d) / base * 100.0) if series.get(d) is not None
                else None for d in dates]

    width = max(11, 9 + n * 0.35)
    fig, ax = plt.subplots(figsize=(width, 6.5))
    marker_size = max(3, 7 - n // 8)
    cmap = plt.get_cmap("tab10")

    for i, name in enumerate(product_order):
        ax.plot(xs, _rebased(nav[name]), marker="o", markersize=marker_size,
                linewidth=1.5, color=cmap(i % 10), label=name)

    ax.plot(xs, _rebased(bench_close["CSI300"]), linestyle="--", marker="s",
            markersize=marker_size, linewidth=2.2, color="#1f6feb",
            label="沪深300")
    ax.plot(xs, _rebased(bench_close["CSI500"]), linestyle=":", marker="^",
            markersize=marker_size, linewidth=2.2, color="#d97706",
            label="中证500")

    ax.axhline(100, color="#888", linewidth=0.8)
    ax.set_xticks(xs)
    ax.set_xticklabels(short_labels, rotation=45, ha="right",
                       fontsize=max(7, 9 - n // 10))
    ax.set_ylabel(f"归一化指数 (首日={dates[0]}=100)")
    ax.set_xlabel("日期")
    ax.set_title(f"基金净值 / 指数点位 归一化波动 ({dates[0]} ~ {dates[-1]})")
    ax.grid(axis="y", linestyle="--", alpha=0.35)

    lh = nav.get("领航1号", {})
    lh0 = lh.get(dates[0])
    cs0 = bench_close["CSI500"].get(dates[0])
    excess_pp = []
    for d in dates:
        lhd, csd = lh.get(d), bench_close["CSI500"].get(d)
        if None not in (lhd, lh0, csd, cs0) and lh0 and cs0:
            excess_pp.append(((lhd / lh0 - 1) - (csd / cs0 - 1)) * 100.0)
        else:
            excess_pp.append(None)
    ax2 = ax.twinx()
    ax2.plot(xs, excess_pp, linestyle="-", marker="D",
             markersize=marker_size + 1, linewidth=2.4, color="#9C0006",
             label="领航1号 - 中证500 累计超额 (右轴)")
    ax2.axhline(0, color="#9C0006", linewidth=0.6, alpha=0.4)
    ax2.set_ylabel("累计超额 (百分点)", color="#9C0006")
    ax2.tick_params(axis="y", labelcolor="#9C0006")

    lines1, labels1 = ax.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax.legend(lines1 + lines2, labels1 + labels2, loc="center left",
              bbox_to_anchor=(1.08, 0.5), fontsize=9, frameon=False)

    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def _build_chart(out_path: Path, extractions: list[Extraction],
                 bench_by_date: dict[str, list[BenchmarkReturn]],
                 product_order: list[str]) -> None:
    _setup_chinese_font()

    dates = [e.date for e in extractions]
    n = len(dates)
    xs = list(range(n))
    short_labels = [d[5:] for d in dates]  # MM-DD
    ytd_grid = _ytd_grid(extractions, product_order)

    # widen figure proportionally for many dates
    width = max(11, 9 + n * 0.35)
    fig, ax = plt.subplots(figsize=(width, 6.5))

    marker_size = max(3, 7 - n // 8)
    cmap = plt.get_cmap("tab10")
    for i, name in enumerate(product_order):
        ys = [ytd_grid[name].get(d) for d in dates]
        ax.plot(xs, ys, marker="o", markersize=marker_size, linewidth=1.6,
                color=cmap(i % 10), label=name)

    bench300 = [bench_by_date[d][0].return_pct for d in dates]
    bench500 = [bench_by_date[d][1].return_pct for d in dates]
    baseline_date = bench_by_date[dates[0]][0].baseline_date
    ax.plot(xs, bench300, linestyle="--", marker="s", markersize=marker_size,
            linewidth=2.2, color="#1f6feb",
            label=f"沪深300 (自{baseline_date}起)")
    ax.plot(xs, bench500, linestyle=":", marker="^", markersize=marker_size,
            linewidth=2.2, color="#d97706",
            label=f"中证500 (自{baseline_date}起)")

    ax.set_xticks(xs)
    ax.set_xticklabels(short_labels, rotation=45, ha="right",
                       fontsize=max(7, 9 - n // 10))
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
        yyyymmdds = sorted(dict.fromkeys(args.dates))

    if not yyyymmdds:
        raise SystemExit("no dates resolved; pass YYYYMMDD args or --range")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    extractions = [_load_sidecar(args.samples_dir, d) for d in yyyymmdds]
    bench_by_date = {e.date: returns_since_march_first(e.date) for e in extractions}
    product_order = _all_product_names(extractions)

    stem = _stem(yyyymmdds)
    md_path = args.out_dir / f"{stem}_table.md"
    csv_path = args.out_dir / f"{stem}_table.csv"
    xlsx_path = args.out_dir / f"{stem}_table.xlsx"
    chart_path = args.out_dir / f"{stem}_chart.png"
    daily_chart_path = args.out_dir / f"{stem}_daily_chart.png"
    nav_chart_path = args.out_dir / f"{stem}_nav_chart.png"
    lh_chart_path = args.out_dir / f"{stem}_lh_chart.png"

    _write_markdown(md_path, extractions, bench_by_date, product_order)
    _write_csv(csv_path, extractions, bench_by_date)
    _build_lh_chart(lh_chart_path, extractions, product_order)
    _write_xlsx(xlsx_path, extractions, bench_by_date, product_order,
                lh_chart_path)
    _build_chart(chart_path, extractions, bench_by_date, product_order)
    _build_daily_chart(daily_chart_path, extractions, product_order)
    _build_nav_chart(nav_chart_path, extractions, product_order)

    print(json.dumps({
        "dates": [e.date for e in extractions],
        "products": product_order,
        "outputs": [str(md_path), str(csv_path), str(xlsx_path),
                    str(chart_path), str(daily_chart_path),
                    str(nav_chart_path), str(lh_chart_path)],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
