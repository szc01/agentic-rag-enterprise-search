r"""验证多轮对话的 localStorage 持久化与清空按钮。

运行：
    cd D:\agentic-rag-system\backend
    ..\.venv\Scripts\python.exe ..\scripts\ui_chat_persist_check.py
"""

import asyncio
from playwright.async_api import async_playwright

URL = "http://127.0.0.1:8000/"
CHROME = r"C:\Users\27809\AppData\Local\Google\Chrome\Application\chrome.exe"


async def wait_last_reply(page, timeout: int = 90_000) -> str:
    loc = page.locator(".msg-assistant .msg-body").last
    await loc.wait_for(timeout=timeout)
    loop = asyncio.get_event_loop()
    start = loop.time()
    while True:
        cls = await loc.get_attribute("class")
        text = await loc.text_content()
        if cls and "streaming" not in cls and text and text.strip() and "思考中" not in text:
            return text
        if (loop.time() - start) * 1000 > timeout:
            raise TimeoutError("等待回答超时")
        await asyncio.sleep(0.5)


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            executable_path=CHROME, headless=True,
            args=["--disable-gpu", "--window-size=1440,1100"],
        )
        page = await browser.new_page(viewport={"width": 1440, "height": 1100})
        await page.goto(URL, wait_until="networkidle", timeout=60_000)
        await page.wait_for_selector("#search-input", timeout=10_000)

        # 先进行一轮对话
        await page.fill("#search-input", "测试对话持久化")
        await page.click("#search-btn")
        await wait_last_reply(page)
        turns_before = await page.locator(".chat-turn").count()
        print(f"对话后轮数: {turns_before}")
        await page.screenshot(path=r"D:\agentic-rag-system\_ui_check_before_refresh.png", full_page=False)

        # 刷新页面，验证 localStorage 恢复
        await page.reload(wait_until="networkidle", timeout=60_000)
        turns_after = await page.locator(".chat-turn").count()
        print(f"刷新后轮数: {turns_after}")
        await page.screenshot(path=r"D:\agentic-rag-system\_ui_check_after_refresh.png", full_page=False)

        # 点击清空对话
        page.on("dialog", lambda dialog: asyncio.create_task(dialog.accept()))
        await page.click("#clear-chat-btn")
        await asyncio.sleep(0.3)
        has_placeholder = await page.locator(".chat-placeholder").count()
        print(f"清空后占位符存在: {has_placeholder > 0}")
        await page.screenshot(path=r"D:\agentic-rag-system\_ui_check_after_clear.png", full_page=False)

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
