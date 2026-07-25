# 信号层：A 波动轴 / B 方向轴 / C 适配轴
import math
import numpy as np
import pandas as pd
from datetime import datetime

from data_feed import (get_price_history, realized_vol, get_near_expirations,
                       get_chain, atm_row)
from catalysts import days_to, catalyst_direction, historical_earnings_move
from config import (MIN_OPTION_VOLUME, MIN_OPTION_OI, MAX_BID_ASK_SPREAD)


def _rolling_rv(closes, window=30):
    rets = closes.pct_change().dropna()
    out = rets.rolling(window).std() * (252 ** 0.5)
    return out.dropna()


def _pct_rank(value, series):
    s = series.dropna()
    if len(s) == 0:
        return 50.0
    return float((s < value).mean() * 100)


def _norm_cdf(x):
    """标准正态 CDF（用 math.erf 精确计算）。"""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _bs_price(S, K, T, r, sigma, kind="call"):
    """Black-Scholes 欧式期权定价。T 为年化时间（年）。"""
    if T <= 0 or sigma <= 0:
        # 退化情形：返回内在价值
        return max(S - K, 0.0) if kind == "call" else max(K - S, 0.0)
    sqrtT = math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * sqrtT)
    d2 = d1 - sigma * sqrtT
    if kind == "call":
        return S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)
    return K * math.exp(-r * T) * _norm_cdf(-d2) - S * _norm_cdf(-d1)


def _mid_price(opt_row):
    """期权中间价：(bid+ask)/2；bid/ask 无效则退用 lastPrice；都无效返回 0。"""
    try:
        b = opt_row.get("bid")
        a = opt_row.get("ask")
        if b == b and a == a and float(b) > 0 and float(a) > 0:
            return 0.5 * (float(b) + float(a))
        lp = opt_row.get("lastPrice")
        if lp == lp and float(lp) > 0:
            return float(lp)
    except Exception:
        pass
    return 0.0


def _implied_vol(S, K, T, r, price, kind="call", lo=1e-4, hi=5.0, tol=1e-7, max_iter=200):
    """二分法从期权价格反解 IV。无解（价格低于内在价值/异常）返回 None。"""
    if price is None or price <= 0:
        return None
    if kind == "call":
        intrinsic = max(S - K * math.exp(-r * T), 0.0)
    else:
        intrinsic = max(K * math.exp(-r * T) - S, 0.0)
    if price <= intrinsic * (1.0 - 1e-9):
        return None
    f_lo = _bs_price(S, K, T, r, lo, kind) - price
    f_hi = _bs_price(S, K, T, r, hi, kind) - price
    if f_lo * f_hi > 0:
        return None
    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        f_mid = _bs_price(S, K, T, r, mid, kind) - price
        if abs(f_mid) < tol:
            return mid
        if f_lo * f_mid < 0:
            hi = mid
            f_hi = f_mid
        else:
            lo = mid
            f_lo = f_mid
    return 0.5 * (lo + hi)


def _skew(chain, spot):
    """约 5% OTM 的 call IV - put IV（同虚值）。>0 看涨偏度。"""
    try:
        cs = chain["calls"]
        ps = chain["puts"]
        c_strike = spot * 1.05
        p_strike = spot * 0.95
        c = cs.iloc[(cs["strike"].astype(float) - c_strike).abs().argsort()[:1]]
        p = ps.iloc[(ps["strike"].astype(float) - p_strike).abs().argsort()[:1]]
        civ = float(c["impliedVolatility"].iloc[0])
        piv = float(p["impliedVolatility"].iloc[0])
        return civ - piv
    except Exception:
        return 0.0


def _liquidity(c, p):
    """0-1 流动性评分：成交量 0.4 + 持仓量 0.3 + 价差 0.3"""
    try:
        score = 0.0
        cv = float(c.get("volume") or 0)
        pv = float(p.get("volume") or 0)
        if max(cv, pv) >= MIN_OPTION_VOLUME:
            score += 0.4
        coi = float(c.get("openInterest") or 0)
        poi = float(p.get("openInterest") or 0)
        if max(coi, poi) >= MIN_OPTION_OI:
            score += 0.3
        c_ask = float(c["ask"]) if c.get("ask") == c.get("ask") and c["ask"] > 0 else float(c["lastPrice"])
        c_bid = float(c["bid"]) if c.get("bid") == c.get("bid") else c_ask
        c_mid = (c_ask + c_bid) / 2.0
        if c_mid > 0 and (c_ask - c_bid) / c_mid <= MAX_BID_ASK_SPREAD:
            score += 0.3
        return min(score, 1.0)
    except Exception:
        return 0.0


def compute_signals(ticker, as_of=None):
    if as_of is None:
        as_of = datetime.now()
    res = {"ticker": ticker}
    df = get_price_history(ticker, years=1)
    if df is None or df.empty:
        res["error"] = "no_price"
        return res
    closes = df["Close"].dropna()
    spot = float(closes.iloc[-1])
    res["spot"] = spot

    # ---- B2 动量 / 趋势 ----
    ret5 = float(closes.iloc[-1] / closes.iloc[-6] - 1) if len(closes) > 6 else 0.0
    ret20 = float(closes.iloc[-1] / closes.iloc[-21] - 1) if len(closes) > 21 else 0.0
    ma20 = float(closes.tail(20).mean())
    ma50 = float(closes.tail(50).mean()) if len(closes) > 50 else ma20
    above_ma20 = 1 if spot > ma20 else 0
    above_ma50 = 1 if spot > ma50 else 0
    res["ret5"] = ret5
    res["ret20"] = ret20
    res["above_ma20"] = above_ma20
    res["above_ma50"] = above_ma50

    # ---- 近月期权链 ----
    near = get_near_expirations(ticker, as_of)
    if not near:
        res["error"] = "no_near_expiry"
        return res
    exp1 = near[0][0]
    res["near_expiry"] = exp1
    res["near_dte"] = near[0][1]
    chain1 = get_chain(ticker, exp1)
    c1 = atm_row(chain1["calls"], spot)
    p1 = atm_row(chain1["puts"], spot)
    if c1 is None or p1 is None:
        res["error"] = "no_atm"
        return res

    # ---- ATM IV：用 BS 从 ATM 期权中间价反解（替代 yfinance 的 impliedVolatility 坏字段）----
    _T = max(float(res["near_dte"]) / 365.0, 1e-6)
    _r = 0.0  # 无风险利率近似（短期期权对 IV 影响 <0.5%）
    _iv_call = _implied_vol(spot, float(c1["strike"]), _T, _r, _mid_price(c1), "call")
    _iv_put = _implied_vol(spot, float(p1["strike"]), _T, _r, _mid_price(p1), "put")
    if _iv_call is None and _iv_put is None:
        # 反解全部失败（极端脏数据），回退到 yfinance 原值，避免崩溃
        atm_iv = float(c1["impliedVolatility"])
        atm_put_iv = float(p1["impliedVolatility"])
    elif _iv_call is None:
        atm_iv = atm_put_iv = _iv_put
    elif _iv_put is None:
        atm_iv = atm_put_iv = _iv_call
    else:
        # call/put 反解通常接近，取均值更稳
        atm_iv = 0.5 * (_iv_call + _iv_put)
        atm_put_iv = atm_iv
    res["atm_iv"] = atm_iv
    res["atm_put_iv"] = atm_put_iv
    res["atm_iv_bs_call"] = _iv_call
    res["atm_iv_bs_put"] = _iv_put

    # ---- A1 IV 百分位（近似：当前 ATM IV 对历史 30 日 RV 分布排位）----
    rv_series = _rolling_rv(closes, 30)
    res["iv_pctile"] = _pct_rank(atm_iv, rv_series)

    # ---- A2 VRP ----
    rv30 = realized_vol(ticker, 30)
    res["rv30"] = rv30
    res["vrp"] = (atm_iv - rv30) if rv30 is not None else 0.0

    # ---- A3 跨期结构 ----
    if len(near) >= 2:
        ch2 = get_chain(ticker, near[1][0])
        c2 = atm_row(ch2["calls"], spot)
        if c2 is not None:
            _iv2 = _implied_vol(spot, float(c2["strike"]), _T, _r, _mid_price(c2), "call")
            iv2 = _iv2 if _iv2 is not None else atm_iv
        else:
            iv2 = atm_iv
        res["term_ratio"] = atm_iv / iv2 if iv2 else 1.0
    else:
        res["term_ratio"] = 1.0

    # ---- A4 定价移动 vs 估计移动 ----
    c_ask = float(c1["ask"]) if (c1.get("ask") == c1.get("ask") and c1["ask"] > 0) else float(c1["lastPrice"])
    p_ask = float(p1["ask"]) if (p1.get("ask") == p1.get("ask") and p1["ask"] > 0) else float(p1["lastPrice"])
    res["call_cost"] = c_ask   # 单边买 Call 成本（ATM call 权利金）
    res["put_cost"] = p_ask   # 单边买 Put 成本（ATM put 权利金）
    straddle = (c_ask + p_ask) / 2.0
    priced_move = 0.85 * straddle / spot
    res["straddle"] = straddle
    res["priced_move"] = priced_move
    est = historical_earnings_move(ticker)
    if est is None:
        absrets = closes.pct_change().dropna().abs()
        est = float(absrets.quantile(0.90)) if len(absrets) else priced_move
    res["est_move"] = est
    res["move_edge"] = est - priced_move

    # ---- B1 催化剂 ----
    res["catalyst"] = days_to(ticker, as_of)
    res["cat_dir"] = catalyst_direction(ticker)  # -1 / 0 / +1

    # ---- B3 偏度 ----
    res["skew"] = _skew(chain1, spot)

    # ---- C 流动性 ----
    res["liquidity"] = _liquidity(c1, p1)
    res["c_volume"] = c1.get("volume")
    res["p_volume"] = p1.get("volume")
    res["c_oi"] = c1.get("openInterest")
    res["p_oi"] = p1.get("openInterest")
    c_mid = (float(c1["ask"]) + float(c1["bid"])) / 2.0 if (c1.get("ask") == c1.get("ask")) else float(c1["lastPrice"])
    p_mid = (float(p1["ask"]) + float(p1["bid"])) / 2.0 if (p1.get("ask") == p1.get("ask")) else float(p1["lastPrice"])
    res["c_spread"] = ((float(c1["ask"]) - float(c1["bid"])) / c_mid) if c_mid else None
    res["p_spread"] = ((float(p1["ask"]) - float(p1["bid"])) / p_mid) if p_mid else None
    return res


if __name__ == "__main__":
    import sys
    tk = sys.argv[1] if len(sys.argv) > 1 else "NVDA"
    import json
    print(json.dumps(compute_signals(tk), default=str, indent=2, ensure_ascii=False))
