# -*- coding: utf-8 -*-
"""两轮对话截图：演示多轮指代消解。"""
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"
OUT = Path(r"D:\agentic-rag-system\report\images")
CHROME = r"C:\Users\27809\AppData\Local\Google\Chrome\Application\chrome.exe"

def ask(page, q):
    page.fill("#search-input", q)
    page.click("#search-btn")
    deadline = time.time() + 90
    while time.time() < deadline:
        streaming = page.locator(".msg-assistant .msg-body.streaming").count()
        err = page.locator(".msg-error").count()
        if err > 0:
            break
        if streaming == 0:
            try:
                txt = page.locator(".msg-assistant .msg-body").last.inner_text()
            except Exception:
                txt = ""
            if txt and txt.strip() != "思考中…" and "思考中" not in txt:
                break
        page.wait_for_timeout(500)
    page.wait_for_timeout(600)

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=CHROME, headless=True, args=["--disable-gpu"])
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
    page = ctx.new_page()
    page.goto(BASE, wait_until="networkidle")
    page.wait_for_timeout(800)

    ask(page, "什么是 RRF 混合检索？")
    ask(page, "它和 BM25 是什么关系？")

    turns = page.locator(".chat-turn").count()
    print("TURNS:", turns)
    for i in range(turns):
        q = page.locator(f".chat-turn:nth-child({i+1}) .msg-user").inner_text()
        a = page.locator(f".chat-turn:nth-child({i+1}) .msg-assistant .msg-body").inner_text()
        print(f"--- Turn {i+1} Q: {q}")
        print(f"    A[{len(a)}]: {a[:160]}")

    page.screenshot(path=str(OUT / "demo_chat_multiturn.png"), full_page=False)
    print("saved demo_chat_multiturn.png")
    browser.close()

print("DONE")
