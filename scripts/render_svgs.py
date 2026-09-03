# -*- coding: utf-8 -*-
"""将 report/images/ 下的自绘 SVG 渲染为高分辨率 PNG。

修复 Chrome headless 把裸文件名当 URL 解析为 DNS 错误页的问题：
使用 file:/// 绝对路径打开 SVG，并通过 device_scale_factor=2 输出 2x 图。
"""
from pathlib import Path
from playwright.sync_api import sync_playwright

CHROME = r"C:\Users\27809\AppData\Local\Google\Chrome\Application\chrome.exe"
IMG_DIR = Path(r"D:\agentic-rag-system\report\images")

# (svg_name, logical_width, logical_height)
# 输出尺寸 = 逻辑尺寸 * 2 (device_scale_factor)
SVG_SPECS = [
    ("flow.svg", 920, 620),    # -> 1840x1240
    ("usecase.svg", 920, 560), # -> 1840x1120
    ("arch.svg", 920, 600),    # -> 1840x1200
    ("er.svg", 920, 620),      # -> 1840x1240
    ("eval.svg", 920, 560),    # -> 1840x1120
]


def render_svg(page, svg_path: Path, png_path: Path, width: int, height: int):
    page.set_viewport_size({"width": width, "height": height})
    page.goto(svg_path.as_uri(), wait_until="networkidle")
    page.wait_for_timeout(300)

    # 校验没有渲染成 Chrome 错误页
    title = page.title()
    body_text = page.inner_text("body") if page.locator("body").count() else ""
    error_markers = ["无法访问此网站", "DNS_PROBE_STARTED", "找不到 ", "的 DNS 地址"]
    if any(m in title or m in body_text for m in error_markers):
        raise RuntimeError(f"{svg_path.name} 渲染为错误页: title={title!r}")

    page.screenshot(path=str(png_path), full_page=False)


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=CHROME,
            headless=True,
            args=["--disable-gpu"],
        )
        # device_scale_factor=2 -> 物理分辨率翻倍，截图更锐利
        ctx = browser.new_context(
            viewport={"width": 920, "height": 620},
            device_scale_factor=2,
        )
        page = ctx.new_page()

        for svg_name, w, h in SVG_SPECS:
            svg_path = IMG_DIR / svg_name
            png_path = IMG_DIR / svg_name.replace(".svg", ".png")
            print(f"render {svg_name} -> {png_path.name} ({w*2}x{h*2})")
            render_svg(page, svg_path, png_path, w, h)

        browser.close()

    print("DONE")


if __name__ == "__main__":
    main()
