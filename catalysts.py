# 催化剂表：由 fetch_calendar.py 从 Nasdaq 公开财报日历自动抓取写回
# 用法：
#   earnings : 未来财报日 "YYYY-MM-DD"（None=未知/ETF/下一季未放出）
#   past     : 过去财报日列表（用于算「历史财报后实际移动中位数」）
#   events   : 自定义事件 [{"date":"YYYY-MM-DD","type":"fda"/"macro"/"merger",
#                             "dir":+1/-1/0,"move":0.08}]
#                 dir +1=偏多 -1=偏空 0=方向不明；move=估计移动比例（可选）
from datetime import datetime

from data_feed import get_price_history

CATALYSTS = {
    "NVDA":  {"earnings": "2026-08-26", "past": ["2026-05-27", "2026-02-25", "2025-11-26", "2025-08-27"], "events": [{'date': '2026-08-26', 'type': 'earnings', 'dir': 0, 'note': 'time-not-supplied'}]},
    "TSLA":  {"earnings": None, "past": ["2026-07-22", "2026-04-22", "2026-01-21", "2025-10-22"], "events": []},
    "AAPL":  {"earnings": "2026-07-30", "past": ["2026-04-30", "2026-01-29", "2025-10-30", "2025-07-31"], "events": [{'date': '2026-07-30', 'type': 'earnings', 'dir': 0, 'note': 'time-after-hours'}]},
    "AMZN":  {"earnings": "2026-07-30", "past": ["2026-04-30", "2026-01-29", "2025-10-30", "2025-07-31"], "events": [{'date': '2026-07-30', 'type': 'earnings', 'dir': 0, 'note': 'time-after-hours'}]},
    "META":  {"earnings": "2026-07-29", "past": ["2026-04-29", "2026-01-28", "2025-10-29", "2025-07-30"], "events": [{'date': '2026-07-29', 'type': 'earnings', 'dir': 0, 'note': 'time-after-hours'}]},
    "GOOGL":  {"earnings": None, "past": ["2026-07-22", "2026-04-22", "2026-01-21", "2025-10-22"], "events": []},
    "MSFT":  {"earnings": "2026-07-29", "past": ["2026-04-29", "2026-01-28", "2025-10-29", "2025-07-30"], "events": [{'date': '2026-07-29', 'type': 'earnings', 'dir': 0, 'note': 'time-after-hours'}]},
    "AMD":  {"earnings": "2026-08-04", "past": ["2026-05-05", "2026-02-03", "2025-11-04", "2025-08-05"], "events": [{'date': '2026-08-04', 'type': 'earnings', 'dir': 0, 'note': 'time-after-hours'}]},
    "NFLX":  {"earnings": None, "past": ["2026-07-16", "2026-04-16", "2026-01-15", "2025-10-16"], "events": []},
    "JPM":  {"earnings": None, "past": ["2026-07-14", "2026-04-14", "2026-01-13", "2025-10-14"], "events": []},
    "XOM":  {"earnings": "2026-07-31", "past": ["2026-05-01", "2026-01-30", "2025-10-31", "2025-08-01"], "events": [{'date': '2026-07-31', 'type': 'earnings', 'dir': 0, 'note': 'time-pre-market'}]},
    "CVX":  {"earnings": "2026-07-31", "past": ["2026-05-01", "2026-01-30", "2025-10-31", "2025-08-01"], "events": [{'date': '2026-07-31', 'type': 'earnings', 'dir': 0, 'note': 'time-pre-market'}]},
    "BAC":  {"earnings": None, "past": ["2026-07-14", "2026-04-14", "2026-01-13", "2025-10-14"], "events": []},
    "SPY":  {"earnings": None, "past": [], "events": []},
    "QQQ":  {"earnings": None, "past": [], "events": []},
    "XLE":  {"earnings": None, "past": [], "events": []},
    "XLF":  {"earnings": None, "past": [], "events": []},
    "GLD":  {"earnings": None, "past": [], "events": []},
}


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
    try:
        closes.index = closes.index.tz_localize(None)
    except Exception:
        pass
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
