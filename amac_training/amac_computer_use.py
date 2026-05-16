#!/usr/bin/env python3
"""
AMAC 培训平台 - Claude Computer Use 自动化
使用 Claude AI 视觉识别并控制电脑，完成基金业协会职业道德课程（30课时）

依赖安装：
    pip install anthropic pyautogui pillow

使用方法：
    1. 在浏览器中手动登录 https://peixun.amac.org.cn/
    2. 设置环境变量：set ANTHROPIC_API_KEY=sk-ant-...
    3. 运行：python amac_computer_use.py
"""

import anthropic
import base64
import os
import sys
import time
from io import BytesIO

try:
    import pyautogui
    from PIL import ImageGrab, Image
except ImportError:
    print("缺少依赖，请运行：pip install pyautogui pillow")
    sys.exit(1)

# ── 配置 ──────────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "sk-frbHt4flPytLzekZ585aEb72Bc59489bA901189c374d383b")
ANTHROPIC_BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "https://api.laozhang.ai")
MODEL = "claude-opus-4-7"
MAX_STEPS = 600          # 最大操作步骤（30课时 × ~20步/课时）
UI_DELAY = 0.6           # 每次操作后等待UI响应的秒数

SYSTEM_PROMPT = """你是一个专门帮助用户在"基金业协会培训平台"完成在线课程的AI助手。

## 你的任务
完成公开课中"职业道德"课程的全部30个课时，具体步骤：
1. 确认当前在培训平台，如需导航到课程页面请先找到"公开课"→"职业道德"
2. 依次点击每个课时/章节，进入视频播放页面
3. 视频加载后：
   - 若可调速，点击播放速度按钮调到 2x 最快速度
   - 等待视频播放完毕（进度条到100%）
4. 视频结束后若出现答题，认真阅读并选择正确答案提交
5. 完成当前课时后返回课程列表，继续下一个课时
6. 直到所有30个课时全部完成

## 操作原则
- 每次操作后等截图显示结果再决定下一步
- 遇到弹窗按提示操作（确认/关闭等）
- 若页面加载中，等待几秒后重新截图
- 若出现登录失效，截图后报告"需要重新登录"停止操作
- 记录已完成的课时编号，避免重复

## 当前状态
用户已在浏览器中完成登录，请直接开始课程任务。"""

# ── 工具函数 ──────────────────────────────────────────────────────────────────

def take_screenshot() -> str:
    """截取全屏并返回 base64 编码的 PNG"""
    img = ImageGrab.grab()
    # 如果分辨率超过 1920×1080，按比例缩小以节省 token
    max_w, max_h = 1920, 1080
    w, h = img.size
    if w > max_w or h > max_h:
        ratio = min(max_w / w, max_h / h)
        img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return base64.standard_b64encode(buf.getvalue()).decode()


def get_screen_size():
    """返回当前屏幕像素尺寸（考虑缩放后的实际分辨率）"""
    img = ImageGrab.grab()
    return img.size  # 返回实际截图尺寸，与 take_screenshot 一致


def execute_action(action: dict) -> str | None:
    """
    执行 Claude 返回的 computer 工具动作。
    成功后返回新截图 base64，若动作本身是 screenshot 则直接返回截图。
    """
    act = action.get("action", "")
    print(f"  [{act}]", end=" ", flush=True)

    if act == "screenshot":
        print()
        return take_screenshot()

    elif act in ("left_click", "right_click", "double_click", "middle_click"):
        x, y = action["coordinate"]
        print(f"({x}, {y})")
        if act == "left_click":
            pyautogui.click(x, y)
        elif act == "right_click":
            pyautogui.rightClick(x, y)
        elif act == "double_click":
            pyautogui.doubleClick(x, y)
        elif act == "middle_click":
            pyautogui.click(x, y, button="middle")

    elif act == "mouse_move":
        x, y = action["coordinate"]
        print(f"({x}, {y})")
        pyautogui.moveTo(x, y, duration=0.2)

    elif act == "left_click_drag":
        sx, sy = action["start_coordinate"]
        ex, ey = action["end_coordinate"]
        print(f"({sx},{sy})→({ex},{ey})")
        pyautogui.moveTo(sx, sy)
        pyautogui.dragTo(ex, ey, duration=0.4, button="left")

    elif act == "type":
        text = action["text"]
        preview = text[:60] + ("…" if len(text) > 60 else "")
        print(f'"{preview}"')
        pyautogui.write(text, interval=0.04)

    elif act == "key":
        key_combo = action["text"]
        print(key_combo)
        keys = key_combo.lower().replace("+", " ").split()
        if len(keys) == 1:
            pyautogui.press(keys[0])
        else:
            pyautogui.hotkey(*keys)

    elif act == "scroll":
        x, y = action["coordinate"]
        direction = action.get("direction", "down")
        amount = int(action.get("amount", 3))
        print(f"({x},{y}) {direction}×{amount}")
        pyautogui.moveTo(x, y, duration=0.1)
        clicks = -amount if direction == "down" else amount
        pyautogui.scroll(clicks)

    elif act == "wait":
        ms = int(action.get("duration", 1000))
        print(f"{ms}ms")
        time.sleep(ms / 1000)

    elif act == "cursor_position":
        x, y = pyautogui.position()
        print(f"→ ({x},{y})")
        return None

    else:
        print(f"未知动作: {act}")
        return None

    time.sleep(UI_DELAY)
    return take_screenshot()


# ── 主循环 ────────────────────────────────────────────────────────────────────

def run():
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, base_url=ANTHROPIC_BASE_URL)
    width, height = get_screen_size()
    print(f"截图分辨率: {width}×{height}")

    tools = [
        {
            "type": "computer_20250124",
            "name": "computer",
            "display_width_px": width,
            "display_height_px": height,
        }
    ]

    print("正在截取初始屏幕…")
    initial_shot = take_screenshot()

    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/png", "data": initial_shot},
                },
                {
                    "type": "text",
                    "text": "这是当前屏幕截图。请开始完成 AMAC 培训平台职业道德课程（30课时）的任务。",
                },
            ],
        }
    ]

    print("\nClaude Computer Use 自动化已启动，按 Ctrl+C 可随时停止\n")

    for step in range(1, MAX_STEPS + 1):
        print(f"\n{'─'*50}")
        print(f"步骤 {step}")

        try:
            response = client.beta.messages.create(
                model=MODEL,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=tools,
                messages=messages,
                betas=["computer-use-2024-10-22"],
            )
        except anthropic.RateLimitError:
            print("API 限速，等待 30 秒后重试…")
            time.sleep(30)
            continue
        except anthropic.APIStatusError as e:
            print(f"API 错误 {e.status_code}: {e.message}")
            if e.status_code >= 500:
                time.sleep(10)
                continue
            raise

        # 构建 assistant 消息内容
        assistant_content = []
        for block in response.content:
            if block.type == "text":
                print(f"Claude: {block.text[:300]}{'…' if len(block.text) > 300 else ''}")
                assistant_content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                assistant_content.append({
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })

        messages.append({"role": "assistant", "content": assistant_content})

        # ── 任务完成检测 ──────────────────────────────────────────────────────
        if response.stop_reason == "end_turn":
            last_text = next(
                (b.text for b in reversed(response.content) if b.type == "text"), ""
            )
            done_keywords = ["全部完成", "已完成所有", "30课时", "任务完成", "需要重新登录"]
            if any(kw in last_text for kw in done_keywords):
                print("\n✓ 任务结束")
                return

            # Claude 暂停但任务未完成，提示继续
            print("Claude 暂停，提示继续…")
            time.sleep(2)
            shot = take_screenshot()
            messages.append({
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": "image/png", "data": shot},
                    },
                    {
                        "type": "text",
                        "text": "请继续完成剩余课时。如果所有30课时已完成请告诉我，否则继续操作。",
                    },
                ],
            })
            continue

        # ── 处理工具调用 ──────────────────────────────────────────────────────
        if response.stop_reason == "tool_use":
            tool_results = []

            for block in response.content:
                if block.type != "tool_use":
                    continue

                screenshot_after = execute_action(block.input)
                if screenshot_after is None:
                    screenshot_after = take_screenshot()

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": screenshot_after,
                            },
                        }
                    ],
                })

            messages.append({"role": "user", "content": tool_results})

    print(f"\n已达到最大步骤数 ({MAX_STEPS})，停止。")


# ── 入口 ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  AMAC 培训平台 — Claude Computer Use 自动化")
    print("=" * 60)
    print()
    print("前提条件：")
    print("  1. 浏览器已登录 https://peixun.amac.org.cn/")
    print("  2. 已安装依赖：pip install anthropic pyautogui pillow")
    print(f"  API: {ANTHROPIC_BASE_URL}")
    print()
    print("注意：运行期间请勿操作鼠标/键盘，Claude 将自动控制。")
    print()
    input("准备好后按 Enter 开始…")
    print()

    try:
        run()
    except KeyboardInterrupt:
        print("\n\n已手动停止。")
