#!/bin/bash
# 一键安装依赖（macOS/Linux）
set -e
echo "安装 Python 依赖..."
pip install playwright
echo "下载 Chromium 浏览器..."
python -m playwright install chromium
echo "✓ 环境准备完毕，可以运行 python amac_training.py"
