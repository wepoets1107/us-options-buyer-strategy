# 美股个股期权买方策略 - 配置

# 固定观察池（160+ 只热门美股，全为期权高流动性标的，2026-07-24 扩容）
WATCHLIST = {
    "mega_growth": [
        "NVDA", "TSLA", "AAPL", "AMZN", "META", "GOOGL", "MSFT", "AMD", "NFLX",
        "AVGO", "ADBE", "CRM", "ORCL", "INTC", "CSCO", "QCOM", "TXN", "AMAT", "MU",
        "PLTR", "NOW", "SNOW", "HUBS", "WDAY", "ZS", "CRWD", "NET", "OKTA",
        "DDOG", "MDB", "SHOP", "SQ", "PYPL", "COIN", "ROKU", "SPOT",
        "UBER", "LYFT", "ABNB", "DASH",
    ],
    "cyclical_fin_energy": [
        "JPM", "BAC", "WFC", "C", "GS", "MS", "USB", "PNC", "BLK", "SCHW",
        "AXP", "COF", "V", "MA", "DFS", "RJF", "TW", "FITB", "TFC", "STT",
        "XOM", "CVX", "COP", "SLB", "OXY", "EOG", "PSX", "VLO", "MPC", "HAL",
        "BKR", "DVN", "OKE", "KMI", "WMB", "EQT", "CAT", "DE", "BA", "GE",
        "HON", "UPS", "FDX", "LMT", "RTX", "NOC", "GD", "WM", "RSG", "PCAR",
        "FAST", "ETN", "PH", "ITW", "IR", "CSX", "UNP", "NSC", "F", "GM",
        "RIVN", "LCID", "NIO", "XPEV", "LI", "STLA", "BRK-B",
    ],
    "consumer_retail": [
        "WMT", "COST", "TGT", "HD", "LOW", "NKE", "SBUX", "MCD", "KO", "PEP",
        "PG", "MDLZ", "MO", "PM", "CVS", "WBA", "DG", "DLTR", "YUM", "CMG",
        "EBAY", "ETSY", "CHWY", "BKNG", "MAR",
    ],
    "healthcare": [
        "JNJ", "PFE", "MRK", "ABBV", "LLY", "UNH", "BMY", "AMGN", "GILD", "VRTX",
        "REGN", "MRNA", "BIIB", "ISRG", "MDT", "SYK", "ABT", "TMO", "DHR", "ZTS",
        "CI", "HUM", "CNC", "WST", "HCA",
    ],
    "event_etf": [
        "SPY", "QQQ", "IWM", "DIA", "GLD", "SLV", "TLT", "XLE", "XLF", "XLK",
        "XLV", "XLI", "KWEB", "EEM", "FXI", "ARKK", "SOXX", "SMH", "XLY", "XLP",
        "XLU", "XLB", "XOP", "KRE", "XRT",
    ],
}

# 网页看板端口（避开 5051/5050/5052）
PORT = 5041

# 流动性硬门槛（universe 过滤，数据到位后启用）
MIN_OPTION_VOLUME = 500        # ATM 期权日均成交量下限
MIN_OPTION_OI = 2000          # 持仓量下限
MAX_BID_ASK_SPREAD = 0.15    # 买卖价差占比上限（相对权利金）

# 波动轴阈值
IV_PCT_CHEAP = 30             # ATM IV 百分位 < 此值 = 便宜（仅展示字段）

# 闸门阈值（校准值，2026-07-24 定）
VRP_OK = 0.12                 # 任何推荐都需「IV 不过分贵」（VRP 未显著高估）
VRP_STRADDLE_MAX = 0.10       # 双买额外 IV 上限（防事件后 IV crush）
MOVE_EDGE_MIN = 0.015         # 双买最小 edge（估计移动-定价移动，占现价比例）
DIR_SUB_MIN = 36.0             # 方向+动量子分下限（防「便宜 IV 假方向」，如 SPY）

# 打分阈值（校准值）
CALL_PUT_THRESH = 60           # 方向分门槛
STRADDLE_THRESH = 55           # 双买分门槛
DIR_GAP = 15                   # 方向差下限（方向够明确才判方向）
BIG_GAP = 25                   # 方向差>=此值优先判方向，否则优先双买

# 打分权重（call/put 对称；straddle 单独）
W_CALL = {
    "dir": 0.30,    # B1 催化剂方向（多）
    "mom": 0.30,    # B2 动量趋势（多）
    "cheap": 0.25,   # A 波动轴便宜度
    "liq": 0.15,     # C1 流动性
}
W_PUT = {
    "dir": 0.30,     # B1 催化剂方向（空）
    "mom": 0.30,     # B2 动量趋势（空）
    "cheap": 0.25,
    "liq": 0.15,
}
W_STRADDLE = {
    "edge": 0.35,     # A4 估计移动 > 定价移动
    "vol": 0.25,       # B2 高波动
    "unclear": 0.25,   # 方向不明（|call-put| 小）
    "cheap": 0.15,     # A 便宜
}

# 买入到期选择（DTE 窗口，避开 7 DTE 的狠 theta）
MIN_DTE = 14
MAX_DTE = 30

# 数据缓存时长（小时）
CACHE_HOURS = 6
