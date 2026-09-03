# -*- coding: utf-8 -*-
"""执行一次真实 Agentic 问答并截图（修正等待逻辑）。"""
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"
OUT = Path(r"D:\agentic-rag-system\report\images")
CHROME = r"C:\Users\27809\AppData\Local\Google\Chrome\Application\chrome.exe"

Q = "什么是 RRF 混合检索？它和 BM25 是什么关系？"

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=CHROME, headless=True, args=["--disable-gpu"])
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
    page = ctx.new_page()
    page.goto(BASE, wait_until="networkidle")
    page.wait_for_timeout(800)

    page.fill("#search-input", Q)
    page.click("#search-btn")

    # 正确等待：回答文本不再是"思考中…"且无 streaming 类，或出现错误
    deadline = time.time() + 90
    done = False
    while time.time() < deadline:
        body = page.locator(".msg-assistant .msg-body").first
        streaming = page.locator(".msg-assistant .msg-body.streaming").count()
        err = page.locator(".msg-error").count()
        if err > 0:
            print("检测到错误气泡")
            done = True
            break
        if streaming == 0:
            try:
                txt = body.inner_text()
            except Exception:
                txt = ""
            if txt and txt.strip() != "思考中…" and "思考中" not in txt:
                done = True
                break
        page.wait_for_timeout(500)

    if not done:
        print("等待超时（90s）")
    page.wait_for_timeout(1200)

    try:
        answer = page.locator(".msg-assistant .msg-body").first.inner_text()
        print("ANSWER_LEN", len(answer))
        print(answer[:600])
    except Exception as e:
        print("读取回答失败", e)
    try:
        meta = page.locator(".msg-assistant .msg-meta").first.inner_text()
        print("META:", meta)
    except Exception as e:
        print("读取 meta 失败", e)
    try:
        cites = page.locator(".msg-citations .citation-card").count()
        print("CITATIONS:", cites)
    except Exception:
        pass
    try:
        print("TRACE_CONF:", page.locator("#trace-confidence").inner_text())
        print("TRACE_LAT:", page.locator("#trace-latency").inner_text())
        print("TRACE_SUBQ:", page.locator("#trace-subqueries").inner_text())
    except Exception:
        pass

    page.screenshot(path=str(OUT / "demo_chat.png"), full_page=False)
    print("saved demo_chat.png")
    browser.close()

print("DONE")
