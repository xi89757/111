---
description: 从最近上传的净值图片中提取数据，更新历史并生成统计表+对比图
---

请按以下流程处理用户最近上传的净值截图（若本轮未上传新图，请说明并停止）：

## 1. 识别图片
从对话中**最近一张**用户上传的图片中提取：
- **日期**：图中标注的报告日 / 截图日期，输出格式 `YYYY-MM-DD`
- **各产品净值**：产品名 → 当日单位净值（浮点数）

## 2. 加载/初始化产品清单
读取 `/home/user/111/data/products.json`：
- **若为空数组**（首次运行）：以本图中识别到的所有产品名作为固定列表，写回该文件
- **若已存在列表**：按既有名称匹配；图中未出现的产品，本日净值字段留空

## 3. 拉取基准指数数据
今天日期是 `2026-05-14`（基准起算日为 `2026-03-01`）。

通过 Tushare MCP 调用 `index_daily` 两次：
- `ts_code="000905.SH"`, `start_date="20260301"`, `end_date="20260514"` → 中证500
- `ts_code="000300.SH"`, `start_date="20260301"`, `end_date="20260514"` → 沪深300

每条记录至少需要 `trade_date` 和 `close` 字段。

## 4. 调用处理脚本
将所有数据拼装为单个 JSON，通过 stdin 传给：

```bash
python3 /home/user/111/scripts/nav_processor.py
```

JSON 结构：

```json
{
  "date": "2026-05-14",
  "navs": {"产品A": 1.2345, "产品B": 0.9876},
  "csi500": [{"trade_date": "20260303", "close": 5800.12}, ...],
  "csi300": [{"trade_date": "20260303", "close": 4100.34}, ...]
}
```

脚本会：
- 把净值追加/更新到 `data/nav_history.csv`
- 更新 `data/benchmark.csv` 缓存
- 写出 `output/stats_table.md` 与 `output/comparison.png`
- 返回 JSON 摘要（含路径与历史行数）

## 5. 回复用户
- 把 `output/stats_table.md` 的表格部分贴到回复里
- 指出 `output/comparison.png` 的绝对路径
- 简要点评本期收益与中证500、沪深300基准的对比
