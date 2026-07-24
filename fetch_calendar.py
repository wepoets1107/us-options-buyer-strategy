# 从公开日历（Nasdaq Earnings Calendar API，免密钥）抓取观察池的财报日，
# 自动写回 catalysts.py 的 CATALYSTS 字典。
# 用法：python fetch_calendar.py  （可加 --start 2026-07-01 --end 2026-08-31）
#
# 说明：
#   Nasdaq 财报日历按「日期」查询，查询日即该票财报日。
#   该 API 的未来数据只覆盖到约未来 1 个月（本机当前约到 2026-08 初），
#   更早 / 更晚的财报（如刚发完的、或下一季在 10 月后的）需从「过去窗口」补。
#   本脚本扫描 [start, end] 全窗口：
#     - 落在今天的财报日 → 记作 earnings（未来催化剂）
#     - 落在今天的财报日 → 记进 past（仅供历史移动估算，days_to 不激活）
#   命中全部观察池即提前停止。
#   ETF（SPY/QQQ/XLE/XLF/GLD）无财报，earnings 留 None。
import os
import sys
import shutil
import json
import time
import urllib.request
from datetime import datetime, timedelta

# ---- SSL 补丁（本机中文用户名路径）----
dst = r"C:/tmp/ca.pem"
try:
    import certifi
    shutil.copyfile(certifi.where(), dst)
    for k in ("CURL_CA_BUNDLE", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE"):
        os.environ[k] = dst
except Exception as e:
    print(f"[ssl] warn: {e}", file=sys.stderr)

from config import WATCHLIST  # noqa: E402

WATCH = [t for v in WATCHLIST.values() for t in v]
ETFS = set(WATCHLIST.get("event_etf", []))
ALIAS = {"GOOG": "GOOGL"}  # Nasdaq 可能用 GOOG 而非 GOOGL
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}
API = "https://api.nasdaq.com/api/calendar/earnings?date={date}"


def fetch(date_str):
    for attempt in range(4):
        try:
            req = urllib.request.Request(API.format(date=date_str), headers=HEADERS)
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < 3:
                time.sleep(1.5 * (attempt + 1))
                continue
            return None
        except Exception:
            return None
    return None


def parse_rows(j):
    if not j:
        return []
    data = j.get("data")
    if isinstance(data, dict):
        return data.get("rows", []) or []
    if isinstance(data, list):
        return data
    return []


def main():
    today = datetime.now()
    today_str = today.strftime("%Y-%m-%d")
    start = sys.argv[sys.argv.index("--start") + 1] if "--start" in sys.argv else "2026-07-01"
    end = sys.argv[sys.argv.index("--end") + 1] if "--end" in sys.argv else "2026-08-31"
    d0 = datetime.strptime(start, "%Y-%m-%d")
    d1 = datetime.strptime(end, "%Y-%m-%d")

    need = set(t for t in WATCH if t not in ETFS)
    future = {}      # tk -> {"date","time"}
    past_map = {}    # tk -> [date_str,...]
    cur = d0
    calls = 0
    while cur <= d1:
        ds = cur.strftime("%Y-%m-%d")
        j = fetch(ds)
        calls += 1
        for r in parse_rows(j):
            sym = (r.get("symbol") or "").upper()
            canon = ALIAS.get(sym, sym)
            if canon not in need:
                continue
            if ds >= today_str:
                if canon not in future:
                    future[canon] = {"date": ds, "time": r.get("time", "") or ""}
                    print(f"  + FUTURE {canon}: {ds} ({future[canon]['time']})")
            else:
                past_map.setdefault(canon, []).append(ds)
        if need <= (set(future) | set(past_map)):
            print(f"  全部 {len(need)} 只已命中，提前停止（{calls} 次请求）。")
            break
        cur += timedelta(days=1)
        time.sleep(0.2)
    else:
        miss = sorted(need - set(future) - set(past_map))
        if miss:
            print(f"  窗口结束，仍未命中：{miss}")

    cats = {}
    for tk in WATCH:
        if tk in ETFS:
            cats[tk] = {"earnings": None, "past": [], "events": []}
            continue
        if tk in future:
            ed = datetime.strptime(future[tk]["date"], "%Y-%m-%d")
            past = [(ed - timedelta(days=91 * i)).strftime("%Y-%m-%d") for i in (1, 2, 3, 4)]
            evs = []
            if future[tk].get("time"):
                evs.append({"date": future[tk]["date"], "type": "earnings",
                            "dir": 0, "note": future[tk]["time"]})
            cats[tk] = {"earnings": future[tk]["date"], "past": past, "events": evs}
        elif tk in past_map:
            ps = sorted(past_map[tk])
            recent = datetime.strptime(ps[-1], "%Y-%m-%d")
            past = [(recent - timedelta(days=91 * i)).strftime("%Y-%m-%d") for i in range(4)]
            cats[tk] = {"earnings": None, "past": past, "events": []}
        else:
            cats[tk] = {"earnings": None, "past": [], "events": []}

    write_catalysts(cats)
    print(f"已写回 catalysts.py（future {len(future)} / past-only {len(past_map)} / 共 {len(need)} 只）。")


def write_catalysts(cats):
    lines = []
    lines.append("# 催化剂表：由 fetch_calendar.py 从 Nasdaq 公开财报日历自动抓取写回")
    lines.append("# 用法：")
    lines.append("#   earnings : 未来财报日 \"YYYY-MM-DD\"（None=未知/ETF/下一季未放出）")
    lines.append("#   past     : 过去财报日列表（用于算「历史财报后实际移动中位数」）")
    lines.append("#   events   : 自定义事件 [{\"date\":\"YYYY-MM-DD\",\"type\":\"fda\"/\"macro\"/\"merger\",")
    lines.append("#                             \"dir\":+1/-1/0,\"move\":0.08}]")
    lines.append("#                 dir +1=偏多 -1=偏空 0=方向不明；move=估计移动比例（可选）")
    lines.append("from datetime import datetime")
    lines.append("")
    lines.append("from data_feed import get_price_history")
    lines.append("")
    lines.append("CATALYSTS = {")
    for tk in WATCH:
        c = cats[tk]
        past_repr = "[" + ", ".join(f'"{p}"' for p in c["past"]) + "]"
        lines.append(f'    "{tk}":  {{"earnings": {py_none(c["earnings"])}, '
                    f'"past": {past_repr}, "events": {c["events"]!r}}},')
    lines.append("}")
    lines.append("")
    lines.append(_HELPERS)
    out = "\n".join(lines)
    with open(os.path.join(os.path.dirname(__file__), "catalysts.py"), "w", encoding="utf-8") as f:
        f.write(out)


def py_none(v):
    return "None" if v is None else f'"{v}"'


_HELPERS = '''
def _parse(d):
    if not d:
        return None
    try:
        return datetime.strptime(d, "%Y-%m-%d")
    except Exception:
        return None

def days_to(ticker, as_of=None):
    """返回最近的未来催化剂 (date_str, days, kind) 或 None。"""
    if as_of is None:
        as_of = datetime.now()
    info = CATALYSTS.get(ticker, {})
    best = None
    e = info.get("earnings")
    de = _parse(e)
    if de is not None and de >= as_of:
        best = (e, (de - as_of).days, "earnings")
    for ev in info.get("events", []):
        dv = _parse(ev.get("date"))
        if dv is not None and dv >= as_of:
            d = (dv - as_of).days
            if best is None or d < best[1]:
                best = (ev.get("date"), d, ev.get("type", "event"))
    return best

def catalyst_direction(ticker):
    """+1 偏多 / -1 偏空 / 0 不明。事件优先，其次财报（财报无内置方向）。"""
    info = CATALYSTS.get(ticker, {})
    evs = info.get("events", [])
    if evs:
        return evs[0].get("dir", 0)
    return 0

def catalyst_move(ticker):
    """事件自带估计移动（若有）"""
    info = CATALYSTS.get(ticker, {})
    evs = info.get("events", [])
    if evs and evs[0].get("move"):
        return evs[0]["move"]
    return None

def historical_earnings_move(ticker):
    """用过去财报日后 1-2 日实际移动中位数，作为估计移动近似。
    需要 CATALYSTS[ticker]['past'] 提供过去财报日。"""
    info = CATALYSTS.get(ticker, {})
    past = info.get("past", [])
    df = get_price_history(ticker, years=1)
    if df is None or not past:
        return None
    closes = df["Close"].dropna()
    closes.index = pd_to_date(closes.index)
    moves = []
    for d in past:
        dd = _parse(d)
        if dd is None:
            continue
        sub = closes[closes.index >= dd]
        if len(sub) >= 2:
            moves.append(abs(sub.iloc[1] / sub.iloc[0] - 1))
    if not moves:
        return None
    moves.sort()
    n = len(moves)
    return moves[n // 2]

def pd_to_date(idx):
    try:
        return idx.date
    except Exception:
        return idx
'''


if __name__ == "__main__":
    main()
