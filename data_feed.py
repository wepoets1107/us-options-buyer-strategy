# 数据层：yfinance 拉取 + 本机 SSL 中文路径补丁 + 缓存
import os
import sys
import shutil
import time
import pickle
from pathlib import Path
from datetime import datetime, timedelta

# ---------------------------------------------------------------------------
# SSL 补丁：部分 Windows 用户名含中文时，curl_cffi(libcurl) 读 certifi 的
# cacert.pem 路径会因中文路径失败（curl: (77)）。修复=把证书复制到
# 纯英文路径，并注入 CURL_CA_BUNDLE / SSL_CERT_FILE / REQUESTS_CA_BUNDLE。
# 必须在 import yfinance / requests 之前执行。
# ---------------------------------------------------------------------------
def apply_ssl_patch():
    dst = r"C:/tmp/ca.pem"
    try:
        import certifi
        src = certifi.where()
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if not os.path.exists(dst) or os.path.getsize(dst) == 0:
            shutil.copyfile(src, dst)
        for k in ("CURL_CA_BUNDLE", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE"):
            os.environ[k] = dst
    except Exception as e:
        print(f"[ssl-patch] warn: {e}", file=sys.stderr)


apply_ssl_patch()

import yfinance as yf  # noqa: E402

CACHE_DIR = Path(__file__).parent / ".cache"
CACHE_DIR.mkdir(exist_ok=True)

from config import CACHE_HOURS, MIN_DTE, MAX_DTE  # noqa: E402


def _cache_path(ticker, kind):
    return CACHE_DIR / f"{ticker}_{kind}.pkl"


def _load_cache(ticker, kind, max_age_hours=CACHE_HOURS):
    p = _cache_path(ticker, kind)
    if p.exists():
        age_h = (time.time() - p.stat().st_mtime) / 3600.0
        if age_h < max_age_hours:
            try:
                return pickle.load(open(p, "rb"))
            except Exception:
                pass
    return None


def _save_cache(ticker, kind, obj):
    try:
        pickle.dump(obj, open(_cache_path(ticker, kind), "wb"))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 价格历史（>=1 年日线）
# ---------------------------------------------------------------------------
def get_price_history(ticker, years=1):
    cached = _load_cache(ticker, "hist")
    if cached is not None:
        return cached
    t = yf.Ticker(ticker)
    df = t.history(period=f"{years}y", interval="1d")
    if df is None or df.empty:
        return None
    _save_cache(ticker, "hist", df)
    return df


def realized_vol(ticker, window=30):
    """近 window 日已实现波动率（年化）"""
    df = get_price_history(ticker, years=1)
    if df is None or len(df) < window + 1:
        return None
    closes = df["Close"].dropna().tail(window + 1)
    rets = closes.pct_change().dropna()
    if len(rets) < 2:
        return None
    return rets.std() * (252 ** 0.5)


# ---------------------------------------------------------------------------
# 期权链
# ---------------------------------------------------------------------------
def get_expirations(ticker):
    cached = _load_cache(ticker, "exps")
    if cached is not None:
        return cached
    t = yf.Ticker(ticker)
    exps = list(t.options)
    _save_cache(ticker, "exps", exps)
    return exps


def get_chain(ticker, expiry, cache_hours=2):
    """返回 {'calls': DataFrame, 'puts': DataFrame}（带 2h 缓存，避免 100+ 只刷新时反复抓取被限流）"""
    cached = _load_cache(ticker, f"chain_{expiry}", max_age_hours=cache_hours)
    if cached is not None:
        return cached
    t = yf.Ticker(ticker)
    ch = t.option_chain(expiry)
    out = {"calls": ch.calls, "puts": ch.puts}
    _save_cache(ticker, f"chain_{expiry}", out)
    return out


def get_near_expirations(ticker, as_of=None):
    """返回落在 [MIN_DTE, MAX_DTE] 窗口内的到期日列表（datetime 对象）"""
    if as_of is None:
        as_of = datetime.now()
    out = []
    for e in get_expirations(ticker):
        try:
            d = datetime.strptime(e, "%Y-%m-%d")
        except Exception:
            continue
        dte = (d - as_of).days
        if MIN_DTE <= dte <= MAX_DTE:
            out.append((e, dte))
    out.sort(key=lambda x: x[1])
    return out


def atm_row(chain_df, spot):
    """找最接近 spot 的 strike 行"""
    if chain_df is None or chain_df.empty:
        return None
    strikes = chain_df["strike"].astype(float)
    idx = (strikes - spot).abs().idxmin()
    return chain_df.loc[idx]


# ---------------------------------------------------------------------------
# 财报 / 催化剂日期
# ---------------------------------------------------------------------------
def get_earnings_date(ticker):
    cached = _load_cache(ticker, "ern", max_age_hours=24)
    if cached is not None:
        return cached
    t = yf.Ticker(ticker)
    result = None
    try:
        cal = t.calendar
        if cal is not None:
            cols = list(cal.columns) if hasattr(cal, "columns") else []
            for c in cols:
                if "earnings" in str(c).lower():
                    v = cal[c].dropna()
                    if len(v):
                        result = str(v.iloc[0])
                        break
    except Exception:
        pass
    if result is None:
        try:
            e = t.earnings
            if e is not None and "Earnings Date" in e.index:
                v = e.loc["Earnings Date"]
                if v is not None and str(v) != "nan":
                    result = str(v)
        except Exception:
            pass
    _save_cache(ticker, "ern", result)
    return result


# ---------------------------------------------------------------------------
# 验证用：打印单票摘要
# ---------------------------------------------------------------------------
def verify(ticker="NVDA"):
    print(f"===== verify {ticker} =====")
    df = get_price_history(ticker, years=1)
    if df is None or df.empty:
        print("  [FAIL] 价格历史拉取失败")
        return
    spot = float(df["Close"].dropna().iloc[-1])
    print(f"  现价: {spot:.2f}")
    print(f"  1年日线行数: {len(df)}")

    rv = realized_vol(ticker, 30)
    print(f"  近30日已实现波动率(年化): {rv:.2%}" if rv is not None else "  已实现波动率: 无")

    exps = get_expirations(ticker)
    print(f"  期权到期日数量: {len(exps)}")
    near = get_near_expirations(ticker)
    print(f"  落在 14-30 DTE 的到期: {near}")

    ern = get_earnings_date(ticker)
    print(f"  财报日期: {ern}")

    if not near:
        print("  [SKIP] 无 14-30 DTE 期权，跳过链解析")
        return
    expiry = near[0][0]
    chain = get_chain(ticker, expiry)
    call = atm_row(chain["calls"], spot)
    put = atm_row(chain["puts"], spot)
    print(f"  近月到期 {expiry} ATM:")
    for name, r in (("CALL", call), ("PUT", put)):
        if r is None:
            print(f"    {name}: 无")
            continue
        iv = r.get("impliedVolatility", float("nan"))
        bid = r.get("bid", float("nan"))
        ask = r.get("ask", float("nan"))
        vol = r.get("volume", float("nan"))
        oi = r.get("openInterest", float("nan"))
        print(f"    {name} strike={float(r['strike']):.2f} IV={iv:.2%} bid={bid} ask={ask} vol={vol} OI={oi}")

    # straddle 定价移动估算
    try:
        c_ask = float(call["ask"]) if call is not None and call.get("ask") == call.get("ask") else float(call["lastPrice"])
        p_ask = float(put["ask"]) if put is not None and put.get("ask") == put.get("ask") else float(put["lastPrice"])
        straddle = (c_ask + p_ask) / 2.0
        priced_move = 0.85 * straddle / spot
        print(f"  ATM straddle 净价≈{straddle:.2f}  定价移动≈{priced_move:.2%}")
    except Exception as e:
        print(f"  straddle 估算失败: {e}")


if __name__ == "__main__":
    tk = sys.argv[1] if len(sys.argv) > 1 else "NVDA"
    verify(tk)
