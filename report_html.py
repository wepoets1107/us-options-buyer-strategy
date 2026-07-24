"""
美股期权买方候选看板 — 静态 HTML 生成器

与 us-etf-strategy 的 reporter.generate_html 同一范式：
数据在生成时刻就烤进 HTML，产出 output/dashboard.html 自包含文件，
直接 present_files 打开即可，不依赖任何服务 / 不二次 fetch / 不跨域。

Flask 服务（web/app.py）仅作为可选的"实时刷新"入口保留；
本文件是默认、稳健的交付形式。
"""
import json
from pathlib import Path

from report import build, OUT as OUTPUT_DIR

HERE = Path(__file__).parent
TEMPLATE = HERE / "web" / "template_static.html"
OUT = OUTPUT_DIR / "dashboard.html"


def render_html(snap: dict) -> str:
    """读取 web/index.html 模板，把 snapshot 内联进 <script> 后返回完整 HTML。"""
    tpl = TEMPLATE.read_text(encoding="utf-8")
    inject = '<script>window.__SNAP__ = ' + json.dumps(snap, ensure_ascii=False) + ';</script>'
    # index.html 模板里已无 fetch，main() 直接读 window.__SNAP__；
    # 在首个 <script> 前注入数据即可。
    html = tpl.replace("<script>", inject + "\n<script>", 1)
    return html


def main():
    snap = build()
    html = render_html(snap)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    rows = snap.get("rows", [])
    cands = [f"{r['ticker']}:{r['label']}" for r in rows
             if r.get("label") not in (None, "none")]
    print(f"静态看板已生成: {OUT}")
    print(f"生成时间: {snap.get('generated')} | 标的 {len(rows)} 只 | 候选: {cands}")


if __name__ == "__main__":
    main()
