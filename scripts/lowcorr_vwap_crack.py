"""Batch-9: crack the vwap-dislocation signal under the 0.25 turnover cap.

Batch-8 got the low-correlation vwap signal to SH 1.63 / TO 0.273 / FIT 1.24
(config W=60 decay=64) -- failing the turnover cap by only 0.023. Heavy inner
ts_mean (K=10) killed Sharpe. This tries LIGHT inner smoothing (K=3/5) of the
close/vwap ratio plus longer windows / high decay to shave the last bit of
turnover while keeping Sharpe > 1.25, then re-checks correlation to champion.

Run:  python scripts/lowcorr_vwap_crack.py
"""

from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import asdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from mining_pipeline.wq_d1_pipeline import submit  # noqa: E402
from scripts.low_corr_mine import fetch_pnl, corr, CHAMPION  # noqa: E402

VENDOR = REPO / "vendor" / "worldquant-miner"
CORR_CEIL = 0.5

COMBOS = [
    # light inner smoothing (K=3/5) of the ratio, long window, high decay
    ("normalize(reverse(ts_av_diff(ts_mean(divide(close, vwap), 3), 60)))", 64),
    ("normalize(reverse(ts_av_diff(ts_mean(divide(close, vwap), 3), 60)))", 32),
    ("normalize(reverse(ts_av_diff(ts_mean(divide(close, vwap), 5), 60)))", 64),
    ("normalize(reverse(ts_av_diff(ts_mean(divide(close, vwap), 5), 40)))", 64),
    # longer raw windows, max decay
    ("normalize(reverse(ts_av_diff(divide(close, vwap), 80)))", 64),
    ("normalize(reverse(ts_av_diff(divide(close, vwap), 100)))", 64),
    # decay_linear inner smoothing (gentler than ts_mean)
    ("normalize(reverse(ts_av_diff(ts_decay_linear(divide(close, vwap), 5), 60)))", 64),
    ("normalize(reverse(ts_av_diff(ts_decay_linear(divide(close, vwap), 3), 60)))", 64),
]
BASE = {"universe": "TOP3000", "delay": 1, "neutralization": "SUBINDUSTRY",
        "truncation": 0.01, "pasteurization": "ON"}


def _load(p, name):
    spec = importlib.util.spec_from_file_location(name, p)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


def main():
    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        print("auth failed"); return 2
    print(f"authenticated as {cm.credentials.username}")
    champ_pnl = fetch_pnl(cm.session, CHAMPION)
    print(f"champion {CHAMPION} PnL days: {len(champ_pnl) if champ_pnl else 0}")
    print(f"running {len(COMBOS)} vwap-crack simulations (delay=1, no IV)")

    out = []
    for i, (expr, decay) in enumerate(COMBOS, 1):
        s = dict(BASE); s["decay"] = decay
        print(f"[{i}/{len(COMBOS)}] decay={decay} :: {expr}")
        res = submit(cm.session, expr, s)
        rec = asdict(res)
        if res.ok:
            c = corr(fetch_pnl(cm.session, res.alpha_id) or {}, champ_pnl) if res.alpha_id else float("nan")
            rec["corr_to_champion"] = c
            print(f"    SH={res.sharpe:+.3f} TO={res.turnover:.3f} DD={res.drawdown:.3f} "
                  f"FIT={res.fitness:+.2f} sub={res.submittable} corr={c:+.3f} alpha={res.alpha_id}")
        else:
            rec["corr_to_champion"] = None
            print(f"    [{res.error[:90]}]")
        out.append(rec)
        with open(REPO / "WQ_MINING_REPORT_batch9.json", "w") as f:
            json.dump(out, f, indent=2)

    good = [r for r in out if r["ok"] and r["submittable"]
            and r["sharpe"] > 1.25 and r["turnover"] < 0.25]
    lowcorr = [r for r in good if r["corr_to_champion"] is not None
               and abs(r["corr_to_champion"]) < CORR_CEIL]
    print("\n" + "=" * 100)
    print(f"submittable: {len(good)}   submittable & |corr|<{CORR_CEIL}: {len(lowcorr)}")
    for r in sorted(out, key=lambda r: -(r["sharpe"] if r["ok"] else -9)):
        if not r["ok"]:
            continue
        c = r.get("corr_to_champion")
        flag = ""
        if r["submittable"] and r["sharpe"] > 1.25 and r["turnover"] < 0.25:
            flag = "SUBMITTABLE" + (" + LOW-CORR ***" if c is not None and abs(c) < CORR_CEIL else "")
        print(f"  SH={r['sharpe']:+.3f} TO={r['turnover']:.3f} DD={r['drawdown']:.3f} "
              f"FIT={r['fitness']:+.2f} corr={c:+.3f} {flag}  decay={r['settings']['decay']} "
              f"alpha={r['alpha_id']}\n      {r['optimized']}")
    print("=" * 100)
    if lowcorr:
        json.dump(lowcorr, open(REPO / "WQ_LOWCORR_RESULTS.json", "w"), indent=2)
        print("wrote WQ_LOWCORR_RESULTS.json")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
