# 固定观察池定义 + 流动性门槛
from config import WATCHLIST, MIN_OPTION_VOLUME, MIN_OPTION_OI, MAX_BID_ASK_SPREAD


def all_tickers():
    """返回 [(ticker, group), ...]"""
    out = []
    for grp, lst in WATCHLIST.items():
        for t in lst:
            out.append((t, grp))
    return out


def ticker_list():
    return [t for t, _ in all_tickers()]


def group_of(ticker):
    for grp, lst in WATCHLIST.items():
        if ticker in lst:
            return grp
    return "unknown"
