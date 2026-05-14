# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 仓库用途

本仓库实现一个"每当用户上传净值截图，自动抽取并对比基准"的小型自动化流程：
- 从图片中识别**日期**与每个**产品的当日净值**
- 与**中证500（000905.SH）**、**沪深300（000300.SH）** 自 **2026-03-01** 以来的累计收益率对比
- 输出统计表（Markdown）与对比图（PNG）

## 目录结构

```
.claude/
  settings.json              # 注册 UserPromptSubmit hook
  hooks/nav_auto_detect.py   # 检测到图片时，注入自动提取流程提示
  commands/nav.md            # `/nav` slash 命令：手动触发提取流程
scripts/
  nav_processor.py           # 归档净值 + 计算收益 + 生成表/图
data/
  products.json              # 固定产品清单（首张图片自动初始化，后续按此匹配）
  nav_history.csv            # 历史净值（按日期 × 产品）
  benchmark.csv              # Tushare 拉取的中证500/沪深300收盘价缓存
output/
  stats_table.md             # 最近一次生成的统计表
  comparison.png             # 最近一次生成的累计收益对比图
requirements.txt             # pandas + matplotlib
```

## 触发方式（二选一即可，已并存）

1. **自动**：`.claude/hooks/nav_auto_detect.py` 在 `UserPromptSubmit` 事件触发。
   若本轮 prompt 含图片相关线索（MIME / 文件名 / "截图"等关键词），自动注入提取流程提示。
2. **手动**：用户输入 `/nav` 显式触发。

两种方式最终都会引导本会话依次执行：
1. 看图 → 提取日期与各产品净值
2. 读 `data/products.json`，空则用本图产品名初始化
3. Tushare MCP `index_daily` 拉两只指数自 `2026-03-01` 至今
4. 拼装 JSON 通过 stdin 喂给 `scripts/nav_processor.py`
5. 把 `output/stats_table.md` 贴到回复里 + 给出 `output/comparison.png` 路径

## 关键约定

- **基准起算日**：硬编码为 `BENCHMARK_START = "2026-03-01"`（见 `scripts/nav_processor.py`）。
  指数收益按 `start_date >= 2026-03-01` 的首个交易日收盘价为基准。
- **产品收益**：每个产品按其历史中 `>= 2026-03-01` 的首个有净值的交易日为基准。
- **产品清单一旦初始化即固定**：之后图中识别到列表外的产品会被忽略；列表内但图中缺失的产品当日留空。
- **日期格式**：脚本里统一 `YYYY-MM-DD`；调用 Tushare 时使用 `YYYYMMDD`。

## 常用命令

```bash
# 安装依赖（已在本机安装）
pip install -r requirements.txt

# 手动驱动一次脚本（也可以从 stdin 传 JSON）
python3 scripts/nav_processor.py --input /tmp/payload.json

# 清空产品清单 / 历史，重新开始
: > data/nav_history.csv && echo '[]' > data/products.json
```

## 开发分支

所有变更提交到分支 `claude/fund-value-extraction-benchmark-qRssj`。
