r"""前端多轮对话 UI 自动化验证

环境要求：
- 后端已启动在 http://127.0.0.1:8000/
- 本机 Chrome 路径与 config.py 一致
- playwright 已安装在项目 venv 中

运行：
    cd D:\agentic-rag-system\backend
    ..\.venv\Scripts\python.exe ..\scripts\ui_multi_turn_check.py
"""

import asyncio
from playwright.async_api import async_playwright

URL = "http://127.0.0.1:8000/"
CHROME = r"C:\Users\27809\AppData\Local\Google\Chrome\Application\chrome.exe"


async def wait_last_reply(page, timeout: int = 90_000) -> str:
    """等待最后一个 assistant 气泡完成流式渲染并返回文本。"""
    loc = page.locator(".msg-assistant .msg-body").last
    await loc.wait_for(timeout=timeout)

    loop = asyncio.get_event_loop()
    start = loop.time()
    while True:
        cls = await loc.get_attribute("class")
        text = await loc.text_content()
        is_streaming = cls and "streaming" in cls
        is_empty = not text or not text.strip() or "思考中" in text
        if not is_streaming and not is_empty:
            return text
        if (loop.time() - start) * 1000 > timeout:
            raise TimeoutError("等待回答流式完成超时")
        await asyncio.sleep(0.5)


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            executable_path=CHROME,
            headless=True,
            args=["--disable-gpu", "--window-size=1440,1100"],
        )
        page = await browser.new_page(viewport={"width": 1440, "height": 1100})
        await page.goto(URL, wait_until="networkidle", timeout=60_000)
        await page.wait_for_selector("#search-input", timeout=10_000)

        rounds = [
            ("什么是 RRF 混合检索？", r"D:\agentic-rag-system\_ui_check_turn1.png"),
            ("它和 BM25 是什么关系？", r"D:\agentic-rag-system\_ui_check_turn2.png"),
        ]

        for idx, (question, shot_path) in enumerate(rounds, 1):
            await page.fill("#search-input", question)
            await page.click("#search-btn")

            answer = await wait_last_reply(page, timeout=90_000)
            print(f"[Round {idx}] Q: {question}")
            print(f"[Round {idx}] A preview: {answer[:200].replace(chr(10), ' ')}")

            await page.screenshot(path=shot_path, full_page=False)
            print(f"[Round {idx}] screenshot saved: {shot_path}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
