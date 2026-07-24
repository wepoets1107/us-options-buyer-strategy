# 打分与分类：call_score / put_score / straddle_score（0-100）
from config import (W_CALL, W_PUT, W_STRADDLE, VRP_OK, VRP_STRADDLE_MAX,
                    MOVE_EDGE_MIN, DIR_SUB_MIN, CALL_PUT_THRESH,
                    STRADDLE_THRESH, DIR_GAP, BIG_GAP)


def _clamp(x):
    return max(0.0, min(100.0, x))


def score(sig):
    if sig is None or "error" in sig:
        return None
    ivp = float(sig.get("iv_pctile", 50.0))
    vrp = float(sig.get("vrp", 0.0))
    priced = float(sig.get("priced_move", 0.0))
    edge = float(sig.get("move_edge", 0.0))
    ret20 = sig.get("ret20", 0.0)
    ret5 = sig.get("ret5", 0.0)
    a20 = sig.get("above_ma20", 0)
    a50 = sig.get("above_ma50", 0)
    cat_dir = sig.get("cat_dir", 0)
    skew = sig.get("skew", 0.0)
    liq = sig.get("liquidity", 0.0)
    rv30 = sig.get("rv30", 0.0) or 0.0

    # ---- A 便宜度（方案A：以 VRP 为核心，iv_pctile 仅展示）----
    if vrp < 0:
        a_cheap = _clamp(100.0 + vrp / 0.20 * 30.0)
    else:
        a_cheap = _clamp(100.0 - max(0.0, vrp) / 0.30 * 100.0)

    # ---- A4 双买 edge ----
    edge_s = _clamp(edge / (priced + 1e-9) * 100)

    # ---- B2 动量（call/put 对称）----
    mom_call = _clamp(50 + ret20 * 200 + ret5 * 100 + a20 * 10 + a50 * 5)
    mom_put = _clamp(50 - ret20 * 200 - ret5 * 100 - a20 * 10 - a50 * 5)

    # ---- B1 催化剂方向 ----
    if cat_dir == 1:
        dir_call, dir_put = 100.0, 0.0
    elif cat_dir == -1:
        dir_call, dir_put = 0.0, 100.0
    else:
        dir_call = dir_put = 50.0

    # ---- C 流动性 ----
    liq_s = liq * 100.0

    # ---- skew 惩罚（贵的一侧扣分）----
    call_skew_pen = max(0.0, skew) * 100.0
    put_skew_pen = max(0.0, -skew) * 100.0

    # ---- 基础分（不含 skew）----
    call_base = (W_CALL["dir"] * dir_call + W_CALL["mom"] * mom_call
                 + W_CALL["cheap"] * a_cheap + W_CALL["liq"] * liq_s)
    put_base = (W_PUT["dir"] * dir_put + W_PUT["mom"] * mom_put
                + W_PUT["cheap"] * a_cheap + W_PUT["liq"] * liq_s)
    call_score = _clamp(call_base - call_skew_pen)
    put_score = _clamp(put_base - put_skew_pen)

    # ---- 波动率 / 方向不明 ----
    vol_s = _clamp(rv30 / 0.80 * 100)
    unclear = _clamp((1 - abs(call_base - put_base) / 100.0) * 100)

    straddle_score = _clamp(
        W_STRADDLE["edge"] * edge_s + W_STRADDLE["vol"] * vol_s
        + W_STRADDLE["unclear"] * unclear + W_STRADDLE["cheap"] * a_cheap)

    # ---- 方向+动量子分（防「便宜 IV 假方向」）----
    dir_sub_call = W_CALL["dir"] * dir_call + W_CALL["mom"] * mom_call
    dir_sub_put = W_PUT["dir"] * dir_put + W_PUT["mom"] * mom_put
    dir_sub = dir_sub_call if call_score >= put_score else dir_sub_put

    # ---- 分类 ----
    # 通用门槛：IV 不过分贵
    iv_ok = vrp <= VRP_OK
    # 方向轴 eligibility：IV 可接受 + 方向分够高 + 方向差够大 + 确有方向/动量倾斜
    max_dir = max(call_score, put_score)
    dir_eligible = (iv_ok and max_dir >= CALL_PUT_THRESH
                    and abs(call_score - put_score) >= DIR_GAP
                    and dir_sub >= DIR_SUB_MIN)
    # 双买轴 eligibility：IV 不贵（防 crush）+ 估计移动明显盖过定价 + 双买分够高
    str_eligible = (vrp <= VRP_STRADDLE_MAX and edge >= MOVE_EDGE_MIN
                    and straddle_score >= STRADDLE_THRESH)

    label = "none"
    if str_eligible and dir_eligible:
        # 方向差大 -> 方向；否则 -> 双买（方向不明但波动大）
        if abs(call_score - put_score) >= BIG_GAP:
            label = "call" if call_score > put_score else "put"
        else:
            label = "straddle"
    elif dir_eligible:
        label = "call" if call_score > put_score else "put"
    elif str_eligible:
        label = "straddle"

    return {
        "ticker": sig.get("ticker"),
        "call_score": round(call_score, 1),
        "put_score": round(put_score, 1),
        "straddle_score": round(straddle_score, 1),
        "iv_pctile": round(ivp, 1),
        "vrp": round(vrp, 4),
        "cheap": iv_ok,
        "priced_move": round(priced, 4),
        "est_move": round(float(sig.get("est_move", 0.0)), 4),
        "move_edge": round(edge, 4),
        "label": label,
    }


if __name__ == "__main__":
    import sys
    from signals import compute_signals
    tk = sys.argv[1] if len(sys.argv) > 1 else "NVDA"
    sig = compute_signals(tk)
    print(score(sig))
