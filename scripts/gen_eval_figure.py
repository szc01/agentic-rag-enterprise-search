# -*- coding: utf-8 -*-
"""生成图 7-1「检索评测消融对比（四组）」SVG 并渲染为 2x PNG。

数据源：backend/output/eval_result.md 的四组消融汇总表。
"""
from pathlib import Path
from playwright.sync_api import sync_playwright

CHROME = r"C:\Users\27809\AppData\Local\Google\Chrome\Application\chrome.exe"
IMG_DIR = Path(r"D:\agentic-rag-system\report\images")

METRICS = [
    ("top-1 命中率", [70.91, 72.73, 69.09, 74.55]),
    ("top-3 命中率", [76.36, 82.73, 81.82, 82.73]),
    ("top-5 命中率", [77.27, 83.64, 89.09, 84.55]),
    ("MRR",            [73.71, 77.80, 76.32, 78.89]),
    ("nDCG@5",         [74.62, 79.24, 79.43, 80.26]),
]
GROUPS = ["BM25-only", "向量-only", "BM25+向量", "完整+Reranker"]
COLORS = ["#c9d2de", "#8fb4e8", "#4a86d8", "#d9774a"]

W, H = 920, 560
TOP, BOTTOM = 70, 470          # 绘图区 y：TOP=100%，BOTTOM=0%
LEFT, RIGHT = 88, 840
PX = (BOTTOM - TOP) / 100.0    # 每个百分点的像素高度


def y_for(pct: float) -> float:
    return BOTTOM - pct * PX


def build_svg() -> str:
    parts = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}" font-family="Microsoft YaHei, PingFang SC, sans-serif">'
    )
    parts.append(f'<rect x="0" y="0" width="{W}" height="{H}" fill="#ffffff"/>')
    parts.append(
        f'<text x="460" y="34" font-size="16" font-weight="bold" '
        f'text-anchor="middle" fill="#1f3a5f">检索评测消融对比（四组，110 条评测集）</text>'
    )

    # 图例
    lx = 300
    for i, (g, c) in enumerate(zip(GROUPS, COLORS)):
        bx = lx + i * 130
        parts.append(f'<rect x="{bx}" y="48" width="16" height="12" rx="3" fill="{c}"/>')
        parts.append(
            f'<text x="{bx + 21}" y="59" font-size="11" fill="#1f3a5f">{g}</text>'
        )

    # 网格线 + Y 轴标签
    for pct, lbl in [(100, "100%"), (75, "75%"), (50, "50%"), (25, "25%"), (0, "0%")]:
        yy = y_for(pct)
        stroke = "#c8c8c8" if pct == 0 else "#e6e6e6"
        parts.append(f'<line x1="{LEFT}" y1="{yy}" x2="{RIGHT}" y2="{yy}" stroke="{stroke}"/>')
        parts.append(
            f'<text x="{LEFT - 6}" y="{yy + 4}" font-size="12" text-anchor="end" fill="#6b6b6b">{lbl}</text>'
        )

    # 5 组指标，每组 4 根柱
    n_groups = len(METRICS)
    n_bars = len(GROUPS)
    group_centers = [LEFT + (RIGHT - LEFT) * (i + 0.5) / n_groups for i in range(n_groups)]
    bar_w = 20
    gap = 5
    total_w = n_bars * bar_w + (n_bars - 1) * gap
    start_offset = -total_w / 2

    for gi, (name, vals) in enumerate(METRICS):
        cx = group_centers[gi]
        for bi, (v, c) in enumerate(zip(vals, COLORS)):
            bx = cx + start_offset + bi * (bar_w + gap)
            by = y_for(v)
            bh = BOTTOM - by
            parts.append(f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bar_w}" height="{bh:.1f}" rx="2" fill="{c}"/>')
            parts.append(
                f'<text x="{bx + bar_w / 2:.1f}" y="{by - 4:.1f}" font-size="9" '
                f'text-anchor="middle" fill="#4a5568">{v:.1f}</text>'
            )
        # X 轴组标签
        parts.append(
            f'<text x="{cx:.0f}" y="492" font-size="12" text-anchor="middle" fill="#1f3a5f">{name}</text>'
        )

    parts.append(
        f'<text x="460" y="520" font-size="10" text-anchor="middle" fill="#8a5f1c">'
        f'注：MRR 与 nDCG@5 为 0–1 区间指标，图中按 ×100 统一到百分比刻度；'
        f'完整管线在 top-1 / MRR / nDCG@5 上最优，top-5 略降为精排「以召回换首位精度」的 trade-off</text>'
    )
    parts.append("</svg>")
    return "\n".join(parts)


def main():
    svg_path = IMG_DIR / "eval.svg"
    png_path = IMG_DIR / "eval.png"
    svg_path.write_text(build_svg(), encoding="utf-8")
    print("written", svg_path)

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME, headless=True, args=["--disable-gpu"])
        ctx = browser.new_context(viewport={"width": 920, "height": 560}, device_scale_factor=2)
        page = ctx.new_page()
        page.goto(svg_path.as_uri(), wait_until="networkidle")
        page.wait_for_timeout(300)
        page.screenshot(path=str(png_path), full_page=False)
        browser.close()
    print("rendered", png_path)


if __name__ == "__main__":
    main()
