# -*- coding: utf-8 -*-
"""截取前端四个模块的演示截图，用于报告「系统演示」小节。"""
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"
OUT = Path(r"D:\agentic-rag-system\report\images")
OUT.mkdir(parents=True, exist_ok=True)

CHROME = r"C:\Users\27809\AppData\Local\Google\Chrome\Application\chrome.exe"

def shot(page, name, view=None, wait=1.0):
    if view:
        page.click(f'.nav-item[data-view="{view}"]')
    page.wait_for_timeout(int(wait * 1000))
    path = OUT / name
    page.screenshot(path=str(path), full_page=False)
    print("saved", name)

with sync_playwright() as p:
    browser = p.chromium.launch(
        executable_path=CHROME,
        headless=True,
        args=["--disable-gpu"],
    )
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
    page = ctx.new_page()
    page.goto(BASE, wait_until="networkidle")
    page.wait_for_timeout(1200)

    # 1. 智能搜索（默认视图）
    shot(page, "demo_search.png", wait=0.8)

    # 2. 知识库
    shot(page, "demo_kb.png", view="kb", wait=1.5)

    # 3. 调研报告
    shot(page, "demo_report.png", view="report", wait=1.5)

    # 4. 运营看板
    shot(page, "demo_dashboard.png", view="dashboard", wait=1.5)

    browser.close()

print("DONE")
