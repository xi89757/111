#!/usr/bin/env python3
"""
UserPromptSubmit hook：当用户在本轮消息中附带了图片时，注入"净值自动提取"流程提示。

Claude Code 在 UserPromptSubmit 事件触发时，将一个 JSON payload（含 prompt 文本与
session 元数据）通过 stdin 传给本脚本。脚本的 stdout 会作为额外的上下文注入到本轮
prompt 中。若未检测到图片相关线索，则静默退出，不会污染上下文。
"""

import json
import re
import sys


IMAGE_HINTS = (
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/webp",
    "image/gif",
    "data:image",
    "[image",
    "<image",
    "attached image",
    "screenshot",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
)

# Chinese cues frequently present when user uploads NAV screenshots
ZH_HINTS = ("截图", "图片", "图中", "上传", "附图", "净值")


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return 0

    prompt = (payload.get("prompt") or "").strip()
    lowered = prompt.lower()

    has_image = any(h in lowered for h in IMAGE_HINTS) or any(h in prompt for h in ZH_HINTS)
    # Heuristic: pasted images in some clients appear as `image_001.png` style refs.
    if not has_image and re.search(r"image[_-]?\d+\.(png|jpe?g|webp)", lowered):
        has_image = True

    if not has_image:
        return 0

    print(
        "## 净值自动提取流程（系统提示）\n"
        "如本轮用户消息附带了 *基金/产品净值截图*，请在不打断用户其他指令的前提下，自动完成下述流程；\n"
        "若图片与净值无关，则忽略本提示。\n\n"
        "**步骤：**\n"
        "1. 识别图片中的报告日期（`YYYY-MM-DD`）与每个产品的最新净值。\n"
        "2. 读取 `/home/user/111/data/products.json`：\n"
        "   - 若为空数组（首次运行），用图中识别到的产品名作为固定列表写回。\n"
        "   - 若已存在，按既有名称匹配；图中未出现的产品，本日净值留空。\n"
        "3. 通过 Tushare MCP 工具 `index_daily` 拉取：\n"
        "   - `ts_code=\"000905.SH\"`, `start_date=\"20260301\"`, `end_date=\"<今天 YYYYMMDD>\"`（中证500）\n"
        "   - `ts_code=\"000300.SH\"`, `start_date=\"20260301\"`, `end_date=\"<今天 YYYYMMDD>\"`（沪深300）\n"
        "4. 将识别结果与两个指数收盘价拼装为 JSON，通过 stdin 传给：\n"
        "   `python3 /home/user/111/scripts/nav_processor.py`\n"
        "   JSON 结构：\n"
        "   ```json\n"
        "   {\n"
        "     \"date\": \"2026-05-14\",\n"
        "     \"navs\": {\"产品A\": 1.2345, \"产品B\": 0.9876},\n"
        "     \"csi500\": [{\"trade_date\": \"20260303\", \"close\": 5800.12}, ...],\n"
        "     \"csi300\": [{\"trade_date\": \"20260303\", \"close\": 4100.34}, ...]\n"
        "   }\n"
        "   ```\n"
        "5. 在回复里展示 `output/stats_table.md` 的内容，并指出 `output/comparison.png` 的路径。\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
