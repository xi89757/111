#!/usr/bin/env python3
"""
nav_processor.py — 净值数据归档 + 基准对比表/图生成器。

输入：通过 stdin 接收 JSON，或通过 --input <path> 指定文件，结构如下：

{
  "date": "2026-05-14",
  "navs": {"产品A": 1.2345, "产品B": 0.9876, ...},
  "csi500": [{"trade_date": "20260303", "close": 5800.12}, ...],
  "csi300": [{"trade_date": "20260303", "close": 4100.34}, ...]
}

- "navs" 中的 key 是产品名，value 是当日净值（float）。
- "csi500" / "csi300" 是从 Tushare index_daily 拿到的原始记录列表
  （只需要 trade_date 与 close 字段，其它字段会被忽略）。
- 若 data/products.json 为空，首张图片的 navs.keys() 会被作为固定产品列表写入。
- 输出写到 output/stats_table.md 与 output/comparison.png。
"""

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib import font_manager


ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUTPUT = ROOT / "output"
PRODUCTS_FILE = DATA / "products.json"
NAV_FILE = DATA / "nav_history.csv"
BENCHMARK_FILE = DATA / "benchmark.csv"

BENCHMARK_START = "2026-03-01"


def _configure_chinese_font() -> None:
    preferred = [
        "Noto Sans CJK SC",
        "Source Han Sans SC",
        "WenQuanYi Zen Hei",
        "WenQuanYi Micro Hei",
        "SimHei",
        "Microsoft YaHei",
        "PingFang SC",
        "Arial Unicode MS",
    ]
    available = {f.name for f in font_manager.fontManager.ttflist}
    chosen = next((name for name in preferred if name in available), None)
    if chosen:
        plt.rcParams["font.sans-serif"] = [chosen] + plt.rcParams["font.sans-serif"]
    plt.rcParams["axes.unicode_minus"] = False


def load_products() -> list[str]:
    if PRODUCTS_FILE.exists():
        return json.loads(PRODUCTS_FILE.read_text(encoding="utf-8"))
    return []


def save_products(products: list[str]) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    PRODUCTS_FILE.write_text(
        json.dumps(products, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def upsert_nav(date_str: str, navs: dict[str, float]) -> list[str]:
    DATA.mkdir(parents=True, exist_ok=True)
    products = load_products()
    if not products:
        products = list(navs.keys())
        save_products(products)

    rows: dict[str, dict[str, str]] = {}
    if NAV_FILE.exists():
        with NAV_FILE.open(encoding="utf-8") as f:
            for r in csv.DictReader(f):
                rows[r["date"]] = r

    rows.setdefault(date_str, {"date": date_str})
    for p in products:
        if p in navs and navs[p] is not None:
            rows[date_str][p] = f"{float(navs[p]):.4f}"
        elif p not in rows[date_str]:
            rows[date_str][p] = ""

    for r in rows.values():
        for p in products:
            r.setdefault(p, "")

    with NAV_FILE.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["date"] + products)
        writer.writeheader()
        for d in sorted(rows.keys()):
            writer.writerow({k: rows[d].get(k, "") for k in ["date"] + products})

    return products


def update_benchmark_cache(csi500: list[dict], csi300: list[dict]) -> pd.DataFrame:
    def normalise(rows: list[dict], col: str) -> pd.DataFrame:
        if not rows:
            return pd.DataFrame(columns=["date", col])
        df = pd.DataFrame(rows)
        date_col = "trade_date" if "trade_date" in df.columns else "date"
        df = df.rename(columns={date_col: "date", "close": col})
        df["date"] = pd.to_datetime(df["date"].astype(str), format="%Y%m%d", errors="coerce")
        df = df.dropna(subset=["date"])
        return df[["date", col]]

    a = normalise(csi500, "csi500")
    b = normalise(csi300, "csi300")
    merged = pd.merge(a, b, on="date", how="outer").sort_values("date").reset_index(drop=True)
    merged["date_str"] = merged["date"].dt.strftime("%Y-%m-%d")
    out = merged[["date_str", "csi500", "csi300"]].rename(columns={"date_str": "date"})
    DATA.mkdir(parents=True, exist_ok=True)
    out.to_csv(BENCHMARK_FILE, index=False)
    return merged.drop(columns=["date_str"])


def build_table_and_chart(products: list[str], benchmark: pd.DataFrame) -> tuple[Path, Path]:
    OUTPUT.mkdir(parents=True, exist_ok=True)

    nav_df = pd.read_csv(NAV_FILE)
    nav_df["date"] = pd.to_datetime(nav_df["date"])
    nav_df = nav_df.sort_values("date").reset_index(drop=True)

    cutoff = pd.to_datetime(BENCHMARK_START)

    bm_filtered = benchmark[benchmark["date"] >= cutoff].copy().reset_index(drop=True)
    if not bm_filtered.empty:
        base500 = bm_filtered["csi500"].dropna().iloc[0] if bm_filtered["csi500"].notna().any() else None
        base300 = bm_filtered["csi300"].dropna().iloc[0] if bm_filtered["csi300"].notna().any() else None
        bm_filtered["csi500_ret"] = (bm_filtered["csi500"] / base500 - 1.0) * 100 if base500 else None
        bm_filtered["csi300_ret"] = (bm_filtered["csi300"] / base300 - 1.0) * 100 if base300 else None

    prod_returns: dict[str, pd.Series] = {}
    for p in products:
        if p not in nav_df.columns:
            continue
        s = pd.to_numeric(nav_df[p], errors="coerce")
        mask = s.notna() & (nav_df["date"] >= cutoff)
        if not mask.any():
            continue
        base = s[mask].iloc[0]
        if not base:
            continue
        prod_returns[p] = pd.Series(
            ((s[mask].values / base) - 1.0) * 100,
            index=nav_df.loc[mask, "date"].values,
        )

    cols = ["日期"] + products + ["中证500", "沪深300"]
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]

    all_dates = sorted(set(nav_df["date"]).union(set(bm_filtered["date"]) if not bm_filtered.empty else set()))
    for d in all_dates:
        row = [d.strftime("%Y-%m-%d")]
        nrow = nav_df[nav_df["date"] == d]
        for p in products:
            v = ""
            if not nrow.empty:
                cell = nrow[p].iloc[0]
                if pd.notna(cell) and str(cell).strip() != "":
                    try:
                        v = f"{float(cell):.4f}"
                    except (TypeError, ValueError):
                        v = str(cell)
            row.append(v or "-")
        if not bm_filtered.empty:
            brow = bm_filtered[bm_filtered["date"] == d]
            if not brow.empty:
                r500 = brow["csi500_ret"].iloc[0] if "csi500_ret" in brow else None
                r300 = brow["csi300_ret"].iloc[0] if "csi300_ret" in brow else None
                row.append(f"{r500:+.2f}%" if pd.notna(r500) else "-")
                row.append(f"{r300:+.2f}%" if pd.notna(r300) else "-")
            else:
                row.extend(["-", "-"])
        else:
            row.extend(["-", "-"])
        lines.append("| " + " | ".join(row) + " |")

    header = (
        f"# 产品净值与基准对比表\n\n"
        f"- 基准起算日：{BENCHMARK_START}\n"
        f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"- 中证500 / 沪深300 数值为相对 {BENCHMARK_START} 首个交易日收盘价的累计收益率\n\n"
    )
    table_path = OUTPUT / "stats_table.md"
    table_path.write_text(header + "\n".join(lines) + "\n", encoding="utf-8")

    _configure_chinese_font()
    fig, ax = plt.subplots(figsize=(12, 6.5))
    for p, s in prod_returns.items():
        ax.plot(s.index, s.values, marker="o", linewidth=1.6, label=p)
    if not bm_filtered.empty:
        if "csi500_ret" in bm_filtered:
            ax.plot(
                bm_filtered["date"], bm_filtered["csi500_ret"],
                label="中证500", linestyle="--", linewidth=2.0, color="#888",
            )
        if "csi300_ret" in bm_filtered:
            ax.plot(
                bm_filtered["date"], bm_filtered["csi300_ret"],
                label="沪深300", linestyle=":", linewidth=2.0, color="#444",
            )
    ax.axhline(0, color="gray", linewidth=0.6, alpha=0.6)
    ax.set_title(f"产品净值收益率 vs 基准（自 {BENCHMARK_START}）")
    ax.set_xlabel("日期")
    ax.set_ylabel("累计收益率 (%)")
    ax.legend(loc="best", fontsize=9)
    ax.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()
    chart_path = OUTPUT / "comparison.png"
    fig.savefig(chart_path, dpi=130)
    plt.close(fig)

    return table_path, chart_path


def main() -> int:
    parser = argparse.ArgumentParser(description="净值数据归档 + 基准对比图生成")
    parser.add_argument("--input", type=Path, help="JSON 输入文件路径；若省略则从 stdin 读取")
    args = parser.parse_args()

    raw = args.input.read_text(encoding="utf-8") if args.input else sys.stdin.read()
    payload = json.loads(raw)

    date_str = payload["date"]
    navs = {k: v for k, v in (payload.get("navs") or {}).items() if v is not None}
    csi500 = payload.get("csi500") or []
    csi300 = payload.get("csi300") or []

    datetime.strptime(date_str, "%Y-%m-%d")

    products = upsert_nav(date_str, navs)
    benchmark = update_benchmark_cache(csi500, csi300)
    table_path, chart_path = build_table_and_chart(products, benchmark)

    print(json.dumps({
        "ok": True,
        "products": products,
        "table": str(table_path),
        "chart": str(chart_path),
        "rows_in_history": sum(1 for _ in NAV_FILE.open(encoding="utf-8")) - 1,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
