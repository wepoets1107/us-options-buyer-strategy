# 报告层：构建全池快照、保存 JSON、计算今日新增信号、导出 CSV
import json
from datetime import datetime
from pathlib import Path

from universe import all_tickers
from signals import compute_signals
from scoring import score
from catalysts import days_to

OUT = Path(__file__).parent / "output"
SNAP = OUT / "snapshot.json"
PREV = OUT / "prev_snapshot.json"


def _cat_str(cat):
    if not cat:
        return None
    return f"{cat[0]}({cat[1]}d,{cat[2]})"


def build():
    rows = []
    for tk, grp in all_tickers():
        sig = compute_signals(tk)
        if "error" in sig:
            rows.append({"ticker": tk, "group": grp, "error": sig["error"]})
            continue
        sc = score(sig)
        if sc is None:
            continue
        rows.append({
            "ticker": tk,
            "group": grp,
            "spot": round(float(sig.get("spot", 0.0)), 2),
            "label": sc["label"],
            "call_score": sc["call_score"],
            "put_score": sc["put_score"],
            "straddle_score": sc["straddle_score"],
            "iv_pctile": sc["iv_pctile"],
            "vrp": sc["vrp"],
            "cheap": sc["cheap"],
            "priced_move": sc["priced_move"],
            "est_move": sc["est_move"],
            "move_edge": sc["move_edge"],
            "near_expiry": sig.get("near_expiry"),
            "near_dte": sig.get("near_dte"),
            "call_cost": round(float(sig.get("call_cost") or 0.0), 2),
            "put_cost": round(float(sig.get("put_cost") or 0.0), 2),
            "straddle_cost": round(float(sig.get("straddle") or 0.0), 2),
            "catalyst": _cat_str(sig.get("catalyst")),
            "cat_dir": sig.get("cat_dir"),
            "skew": round(float(sig.get("skew") or 0.0), 4),
            "liquidity": round(float(sig.get("liquidity") or 0.0), 2),
            "rv30": round(float(sig.get("rv30") or 0.0), 4),
        })
    snap = {"generated": datetime.now().strftime("%Y-%m-%d %H:%M"), "rows": rows}
    snap["new_today"] = new_today(snap)
    return snap


def save(snap):
    OUT.mkdir(exist_ok=True)
    if SNAP.exists():
        try:
            PREV.write_text(SNAP.read_text(encoding="utf-8"), encoding="utf-8")
        except Exception:
            pass
    SNAP.write_text(json.dumps(snap, ensure_ascii=False, indent=2, default=str),
                   encoding="utf-8")


def new_today(snap):
    if not PREV.exists():
        return []
    try:
        prev = json.loads(PREV.read_text(encoding="utf-8"))
    except Exception:
        return []
    prev_map = {r["ticker"]: r.get("label") for r in prev.get("rows", [])}
    out = []
    for r in snap["rows"]:
        lab = r.get("label")
        if lab not in (None, "none") and prev_map.get(r["ticker"], "none") in (None, "none"):
            out.append(r["ticker"])
    return out


def to_csv(snap, path=None):
    import csv
    path = path or (OUT / "snapshot.csv")
    OUT.mkdir(exist_ok=True)
    cols = ["ticker", "group", "label", "call_score", "put_score", "straddle_score",
            "iv_pctile", "vrp", "cheap", "priced_move", "est_move", "move_edge",
            "near_expiry", "near_dte", "straddle_cost", "catalyst", "cat_dir",
            "skew", "liquidity", "rv30", "spot"]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in snap["rows"]:
            row = {c: r.get(c, "") for c in cols}
            w.writerow(row)
    return path


if __name__ == "__main__":
    snap = build()
    save(snap)
    to_csv(snap)
    cands = [f"{r['ticker']}:{r['label']}" for r in snap["rows"] if r.get("label") not in (None, "none")]
    print(f"生成 {len(snap['rows'])} 只 | 候选: {cands}")
    print(f"今日新增: {snap['new_today']}")
