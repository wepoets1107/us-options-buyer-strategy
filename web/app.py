# 网页看板（实时刷新，端口 5060，避开 5051/5050/5052）
# 范式对齐 options-eye：后台线程定时重建快照 + 前端 fetch('/api/snapshot') 轮询。
# 额外保险：首屏把快照内联进 HTML，杜绝"加载中…"空白；前端每 30s 轮询刷新。
import json
import threading
import time
from pathlib import Path

from flask import Flask, jsonify, request
import config
import report

WEB = Path(__file__).parent
HERE = WEB.parent
SNAP = HERE / "output" / "snapshot.json"

app = Flask(__name__, static_folder=None)

_state = {"snap": None}
_lock = threading.Lock()
_refresh_secs = 900  # 15 分钟重建一次快照（yfinance 免费源，避免过频）


def _build():
    """重建快照并写盘，返回新快照。"""
    snap = report.build()
    try:
        SNAP.write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    with _lock:
        _state["snap"] = snap
    return snap


def _current_snap():
    with _lock:
        return _state["snap"]


def _bg_loop():
    # 立即构建一次，之后每 _refresh_secs 重建（范式对齐 options-eye：服务先起、数据随后填）
    while True:
        try:
            _build()
        except Exception as e:
            print(f"[bg] 快照重建失败: {e}")
        time.sleep(_refresh_secs)


@app.route("/")
def index():
    # 使用 template_static.html（5030 已验证能渲染），内联 snapshot 数据做首屏，
    # 同时注入 fetch 轮询代码做实时刷新。
    html = (WEB / "template_static.html").read_text(encoding="utf-8")
    snap = _current_snap()
    if snap is not None:
        inject = '<script>window.__SNAP__ = ' + json.dumps(snap, ensure_ascii=False) + ';</script>'
        html = html.replace("<script>", inject + "\n<script>", 1)
        # 在 main(); 后追加实时刷新轮询
        fetch_script = '''
// ---- 实时刷新轮询（对齐 options-eye 范式）----
async function fetchData() {
  try {
    const r = await fetch('/api/snapshot');
    if (!r.ok) return;
    const d = await r.json();
    if (d.rows && d.rows.length) {
      window.__SNAP__ = d;
      main();
    }
  } catch(e) {}
}
setInterval(fetchData, 30000);
fetchData();
'''
        html = html.replace("main();", "main();" + fetch_script, 1)
    return html


@app.route("/api/snapshot")
def snapshot():
    """实时快照（后台线程定时重建，前端轮询刷新）。"""
    snap = _current_snap()
    if snap is None:
        return jsonify({"generated": None, "rows": [], "new_today": []})
    return jsonify(snap)


@app.route("/api/refresh", methods=["POST"])
def refresh_now():
    """手动立即重建快照。"""
    try:
        _build()
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


def serve():
    # 先灌入已落盘的快照，保证首屏立刻有数据（不阻塞 HTTP 启动）
    if SNAP.exists():
        try:
            _state["snap"] = json.loads(SNAP.read_text(encoding="utf-8"))
            print(f"[serve] 已载入落盘快照（首屏有数据）")
        except Exception as e:
            print(f"[serve] 载入落盘快照失败: {e}")
    # 后台线程异步构建（立即构建一次，随后每 _refresh_secs 重建）
    # 范式对齐 options-eye：HTTP 服务先起，数据随后填充，绝不阻塞在 _build
    t = threading.Thread(target=_bg_loop, daemon=True)
    t.start()
    print(f"[serve] Web 看板: http://127.0.0.1:{config.PORT}")
    app.run(host="127.0.0.1", port=config.PORT, threaded=True)


if __name__ == "__main__":
    serve()
