#!/usr/bin/env python3
"""
基金业协会培训平台自动化脚本
目标：完成公开课 -> 职业道德课程（30课时）+ 每主题答题
用法：python amac_training.py
  → 脚本自动打开浏览器，等你手动登录后按回车，自动接管后续操作
"""

import asyncio
import json
import os
import sys
import time
import logging
from pathlib import Path
from datetime import datetime
from playwright.async_api import async_playwright, Page, BrowserContext, TimeoutError as PlaywrightTimeout

# ─── 配置 ────────────────────────────────────────────────────────────────────
BASE_URL       = "https://peixun.amac.org.cn"
COOKIES_FILE   = Path(__file__).parent / "cookies.json"   # 可选，有则自动载入
PROGRESS_FILE  = Path(__file__).parent / "progress.json"
LOG_FILE       = Path(__file__).parent / "training.log"
HEADLESS       = False   # 必须 False，需要可见浏览器让你登录
VIDEO_TIMEOUT  = 7200    # 单个视频最长等待秒数（2小时兜底）
SPEED_FACTOR   = 2.0     # 视频倍速（若平台允许）
# ─────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# Cookie 管理
# ══════════════════════════════════════════════════════════════════════════════

def load_progress() -> dict:
    if PROGRESS_FILE.exists():
        return json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
    return {"completed_ids": [], "completed_titles": []}


def save_progress(progress: dict):
    PROGRESS_FILE.write_text(
        json.dumps(progress, ensure_ascii=False, indent=2), encoding="utf-8"
    )


async def apply_cookies(context: BrowserContext):
    """载入已保存的 Cookie（可选）。"""
    if COOKIES_FILE.exists():
        cookies = json.loads(COOKIES_FILE.read_text(encoding="utf-8"))
        await context.add_cookies(cookies)
        log.info(f"已载入已保存的 Cookie（{len(cookies)} 条）")
    else:
        log.info("无已保存的 Cookie，将在浏览器中等待手动登录")


# ══════════════════════════════════════════════════════════════════════════════
# 视频播放
# ══════════════════════════════════════════════════════════════════════════════

async def wait_for_video_end(page: Page, lesson_title: str) -> bool:
    """等待视频播放完成，自动尝试倍速/跳转。"""
    try:
        await page.wait_for_selector("video", timeout=20_000)
    except PlaywrightTimeout:
        log.warning(f"  [{lesson_title}] 未检测到 <video> 元素，跳过视频等待")
        return False

    # 确认视频已开始
    await asyncio.sleep(2)
    await page.evaluate("() => { const v = document.querySelector('video'); if(v && v.paused) v.play(); }")

    # 读取时长
    duration = await page.evaluate(
        "() => { const v = document.querySelector('video'); return v ? v.duration : 0; }"
    )
    log.info(f"  视频时长: {duration:.0f}s ({duration/60:.1f} min)")

    # 尝试 2x 倍速
    actual_rate = await page.evaluate(f"""() => {{
        const v = document.querySelector('video');
        if (!v) return 1;
        v.playbackRate = {SPEED_FACTOR};
        return v.playbackRate;
    }}""")
    if actual_rate >= 1.5:
        log.info(f"  倍速已设置为 {actual_rate}x")

    # 尝试跳转到接近末尾（部分平台阻止）
    seeked = await page.evaluate("""() => {
        const v = document.querySelector('video');
        if (!v || !isFinite(v.duration) || v.duration < 10) return false;
        const target = v.duration - 3;
        v.currentTime = target;
        return Math.abs(v.currentTime - target) < 5;
    }""")
    if seeked:
        log.info("  已跳转到视频末尾（平台允许 seek）")
        await asyncio.sleep(5)
        return True

    # 不能跳转 → 真实等待（除以倍速）
    wait_sec = (duration / actual_rate + 10) if duration > 0 else 1800
    log.info(f"  平台不允许 seek，等待约 {wait_sec:.0f}s …")

    deadline = time.time() + min(wait_sec * 1.2, VIDEO_TIMEOUT)
    while time.time() < deadline:
        ended = await page.evaluate("""() => {
            const v = document.querySelector('video');
            if (!v) return true;
            return v.ended || (isFinite(v.duration) && v.currentTime >= v.duration - 1);
        }""")
        if ended:
            log.info("  ✓ 视频已播放完毕")
            return True
        await asyncio.sleep(5)

    log.warning("  ⚠ 等待超时，视频可能未完成")
    return False


# ══════════════════════════════════════════════════════════════════════════════
# 答题处理
# ══════════════════════════════════════════════════════════════════════════════

# 选项优先顺序：先选最后一个，若错了依次回退（简单策略）
ANSWER_STRATEGY = "last_first"   # "first" | "last_first" | "interactive"

async def answer_quiz(page: Page) -> bool:
    """检测并完成当前页面的答题环节。"""
    # 等待弹窗或页面变化
    await asyncio.sleep(3)

    # 常见题目容器选择器（按优先级排列）
    q_selectors = [
        ".question-item", ".exam-question", ".quiz-item",
        "[class*='question']", "[class*='题目']",
        "li.option", ".el-radio-group", ".el-checkbox-group",
    ]

    questions = []
    for sel in q_selectors:
        questions = await page.query_selector_all(sel)
        if questions:
            log.info(f"  检测到 {len(questions)} 道题目（selector: {sel}）")
            break

    if not questions:
        log.info("  未检测到答题模块，继续下一课")
        return True

    for idx, q in enumerate(questions):
        log.info(f"  答题: 第 {idx+1}/{len(questions)} 题")

        # 提取题目文字（用于日志）
        q_text = await q.inner_text()
        q_text = q_text.strip().replace("\n", " ")[:80]
        log.info(f"    题目: {q_text}")

        # 找选项（radio / checkbox）
        options = await q.query_selector_all("input[type='radio'], input[type='checkbox']")
        if not options:
            # 备用：找 li.option 或 div.option
            options = await q.query_selector_all("li, .option, .answer-item, [class*='option']")

        if not options:
            log.warning("    未找到选项，跳过本题")
            continue

        if ANSWER_STRATEGY == "interactive":
            # 打印选项，让用户在浏览器中手动选择后按 Enter 继续
            log.info("    [interactive] 请在浏览器中手动选择答案，然后在终端按 Enter")
            input()
        elif ANSWER_STRATEGY == "last_first":
            await options[-1].click()
            await asyncio.sleep(0.3)
        else:
            await options[0].click()
            await asyncio.sleep(0.3)

    # 提交按钮
    submit_selectors = [
        "button[type='submit']",
        "button:has-text('提交')", "button:has-text('确定')",
        "button:has-text('完成')", "button:has-text('下一题')",
        ".submit-btn", ".confirm-btn", "[class*='submit']",
    ]
    for sel in submit_selectors:
        btn = await page.query_selector(sel)
        if btn:
            await btn.click()
            log.info("  ✓ 已点击提交按钮")
            await asyncio.sleep(2)
            break
    else:
        log.warning("  未找到提交按钮，请手动检查")

    # 处理提交后可能出现的弹窗（"答错了，重新作答"）
    await handle_retry_dialog(page)

    return True


async def handle_retry_dialog(page: Page):
    """处理答错重答提示弹窗。"""
    retry_texts = ["重新作答", "再次答题", "重答", "retry"]
    for text in retry_texts:
        try:
            btn = page.get_by_text(text, exact=False)
            if await btn.count() > 0:
                log.info(f"  检测到重答提示，点击『{text}』重新作答")
                await btn.click()
                await asyncio.sleep(1)
                await answer_quiz(page)   # 递归重答
                return
        except Exception:
            pass

    # 处理确认弹窗
    ok_texts = ["确定", "知道了", "继续", "好的", "OK"]
    for text in ok_texts:
        try:
            btn = page.get_by_text(text, exact=False)
            if await btn.count() > 0:
                await btn.click()
                await asyncio.sleep(1)
                return
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════════════════
# 课程导航
# ══════════════════════════════════════════════════════════════════════════════

async def navigate_to_zhiye_daode(page: Page) -> bool:
    """导航到公开课 -> 职业道德课程页面。"""
    log.info("正在打开培训平台首页 …")
    await page.goto(BASE_URL, wait_until="networkidle", timeout=30_000)
    await asyncio.sleep(2)

    # 点击「公开课」菜单
    menu_selectors = [
        "a:has-text('公开课')", "[class*='menu'] a:has-text('公开课')",
        "nav a:has-text('公开课')", "li:has-text('公开课') > a",
    ]
    clicked = False
    for sel in menu_selectors:
        try:
            el = page.locator(sel).first
            if await el.count() > 0:
                await el.click()
                clicked = True
                log.info(f"  已点击「公开课」菜单（{sel}）")
                await asyncio.sleep(2)
                break
        except Exception:
            pass

    if not clicked:
        log.warning("未能找到「公开课」菜单，尝试直接搜索课程")

    # 查找「职业道德」课程入口
    course_selectors = [
        "a:has-text('职业道德')",
        "[class*='course']:has-text('职业道德') a",
        ".course-card:has-text('职业道德')",
        "div:has-text('职业道德') >> a",
    ]
    for sel in course_selectors:
        try:
            el = page.locator(sel).first
            if await el.count() > 0:
                await el.click()
                log.info("  已进入「职业道德」课程")
                await page.wait_for_load_state("networkidle")
                return True
        except Exception:
            pass

    log.error("未能找到「职业道德」课程，请检查网络或手动导航后重试")
    return False


async def get_lesson_list(page: Page) -> list[dict]:
    """
    解析课程页面内的课时列表。
    返回 [{"id": ..., "title": ..., "element_selector": ...}, ...]
    """
    await asyncio.sleep(2)

    # 常见课时列表选择器
    lesson_selectors = [
        ".lesson-item", ".chapter-item", ".catalog-item",
        "[class*='lesson']", "[class*='chapter']",
        "ul.course-list li", ".course-section li",
        ".section-item", ".video-item",
    ]

    lessons = []
    for sel in lesson_selectors:
        items = await page.query_selector_all(sel)
        if len(items) >= 3:
            log.info(f"找到 {len(items)} 个课时条目（selector: {sel}）")
            for i, item in enumerate(items):
                title = (await item.inner_text()).strip().replace("\n", " ")[:60]
                lessons.append({
                    "index": i,
                    "title": title,
                    "selector": f"{sel}:nth-child({i+1})",
                })
            break

    if not lessons:
        log.warning("未能自动解析课时列表，将尝试逐个点击章节")

    return lessons


# ══════════════════════════════════════════════════════════════════════════════
# 主流程
# ══════════════════════════════════════════════════════════════════════════════

async def process_lesson(page: Page, lesson: dict, progress: dict) -> bool:
    """处理单个课时：播放视频 + 答题。"""
    title = lesson["title"]
    lesson_id = str(lesson["index"])

    if lesson_id in progress["completed_ids"]:
        log.info(f"[跳过] {title}（已完成）")
        return True

    log.info(f"\n{'─'*60}")
    log.info(f"开始课时 [{lesson['index']+1}]: {title}")

    # 点击课时
    try:
        items = await page.query_selector_all(lesson["selector"].rsplit(":nth-child", 1)[0])
        target = items[lesson["index"]]
        await target.scroll_into_view_if_needed()
        await target.click()
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(2)
    except Exception as e:
        log.error(f"  点击课时失败: {e}")
        return False

    # 播放视频
    video_ok = await wait_for_video_end(page, title)

    # 等待并处理答题
    await answer_quiz(page)

    # 标记完成
    if video_ok:
        progress["completed_ids"].append(lesson_id)
        progress["completed_titles"].append(title)
        save_progress(progress)
        log.info(f"  ✓ 课时完成: {title}")

    return video_ok


async def wait_for_login(page: Page):
    """打开平台首页，等待用户手动登录后按 Enter 继续。"""
    # 删除可能过期的旧 Cookie，避免误判
    if COOKIES_FILE.exists():
        COOKIES_FILE.unlink()
        log.info("已清除旧 Cookie，重新登录")

    log.info("正在打开培训平台 …")
    await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30_000)

    print("\n" + "="*60)
    print("  浏览器已打开，请手动登录基金业协会培训平台。")
    print("  登录完成后，回到此终端窗口按 Enter 继续。")
    print("="*60)

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, input, "\n登录完成后按 Enter: ")

    # 保存 Cookie 供下次复用
    cookies = await page.context.cookies()
    COOKIES_FILE.write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(f"✓ Cookie 已保存，共 {len(cookies)} 条")


async def run():
    progress = load_progress()
    completed = len(progress["completed_ids"])
    log.info(f"已完成课时: {completed}，继续从断点开始")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=HEADLESS,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        # 隐藏自动化特征
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        page = await context.new_page()

        # 每次都等用户手动登录后按 Enter
        await wait_for_login(page)

        # 导航到职业道德课程
        ok = await navigate_to_zhiye_daode(page)
        if not ok:
            log.error("导航失败，请在浏览器中手动进入职业道德课程后按 Enter")
            input("手动导航完成后，按 Enter 继续 ...")

        # 获取课时列表
        lessons = await get_lesson_list(page)

        if not lessons:
            log.warning(
                "\n自动解析课时列表失败，切换为「手动引导模式」：\n"
                "  请在浏览器中依次点击每个课时，脚本会自动等待视频完成并处理答题。\n"
                "  每完成一课时，脚本自动检测并进入下一课时（等待 5 秒）。\n"
                "  按 Ctrl+C 可随时退出，进度已自动保存。"
            )
            await manual_guided_mode(page, progress)
        else:
            # 自动模式：逐课时处理
            for lesson in lessons:
                await process_lesson(page, lesson, progress)

        log.info(f"\n{'═'*60}")
        log.info(f"全部课时处理完毕！完成: {len(progress['completed_ids'])} 课时")
        log.info(f"进度已保存至 {PROGRESS_FILE}")

        input("\n按 Enter 关闭浏览器 ...")
        await browser.close()


async def manual_guided_mode(page: Page, progress: dict):
    """
    课时列表无法自动解析时的兜底模式：
    监测 URL/页面变化，自动触发视频等待和答题。
    """
    last_url = page.url
    session_count = 0
    MAX_LESSONS = 30

    while session_count < MAX_LESSONS:
        current_url = page.url
        if current_url != last_url:
            last_url = current_url
            lesson_id = current_url.split("/")[-1]
            title = await page.title()
            log.info(f"\n检测到页面跳转: {title} ({current_url})")

            if lesson_id not in progress["completed_ids"]:
                await wait_for_video_end(page, title)
                await answer_quiz(page)
                progress["completed_ids"].append(lesson_id)
                progress["completed_titles"].append(title)
                save_progress(progress)
                session_count += 1
                log.info(f"✓ 已完成 {session_count} 课时")
            else:
                log.info("（已完成，跳过）")

        await asyncio.sleep(5)


if __name__ == "__main__":
    log.info("=" * 60)
    log.info("基金业协会培训平台 - 职业道德课程自动化脚本")
    log.info(f"启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info("=" * 60)
    asyncio.run(run())
