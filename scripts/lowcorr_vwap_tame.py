"""Batch-8: tame the turnover of the low-correlation vwap-dislocation signal.

Batch-7 found that the vwap-dislocation reversion
    normalize(reverse(ts_av_diff(divide(close, vwap), 20)))
scores SH 1.70 / DD 0.074 with only +0.11 PnL correlation to the close-
reversion champion rKomaon1 -- i.e. a strong, diversifying, low-drawdown
signal. Its only failing is turnover 0.688 (it is a fast intraday reversion).

This sweeps longer windows + heavier decay + inner smoothing to crush
turnover under 0.25 while holding Sharpe > 1.25, then re-checks PnL
correlation to the champion (heavier smoothing can drift it toward the
close-reversion factor).

Run:  python scripts/lowcorr_vwap_tame.py
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

# (expression, decay) -- longer windows + inner ts_mean smoothing + high decay.
COMBOS = []
for W in (20, 40, 60):
    for decay in (16, 32, 64):
        COMBOS.append((f"normalize(reverse(ts_av_diff(divide(close, vwap), {W})))", decay))
# inner-smoothed variants (smooth the ratio before differencing the level)
for W, K in ((40, 10), (60, 10), (60, 20)):
    COMBOS.append((f"normalize(reverse(ts_mean(ts_av_diff(divide(close, vwap), {W}), {K})))", 16))

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
    print(f"running {len(COMBOS)} vwap-taming simulations (delay=1, no IV)")

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
                  f"FIT={res.fitness:+.2f} sub={res.submittable} "
                  f"corr={c:+.3f} alpha={res.alpha_id}")
        else:
            rec["corr_to_champion"] = None
            print(f"    [{res.error[:90]}]")
        out.append(rec)
        with open(REPO / "WQ_MINING_REPORT_batch8.json", "w") as f:
            json.dump(out, f, indent=2)

    good = [r for r in out if r["ok"] and r["submittable"]
            and r["sharpe"] > 1.25 and r["turnover"] < 0.25]
    lowcorr = [r for r in good if r["corr_to_champion"] is not None
               and abs(r["corr_to_champion"]) < CORR_CEIL]
    print("\n" + "=" * 100)
    print(f"submittable: {len(good)}   submittable & |corr|<{CORR_CEIL}: {len(lowcorr)}")
    for r in sorted(good, key=lambda r: -r["sharpe"]):
        c = r.get("corr_to_champion")
        flag = "LOW-CORR ***" if (c is not None and abs(c) < CORR_CEIL) else ""
        print(f"  SH={r['sharpe']:+.3f} TO={r['turnover']:.3f} DD={r['drawdown']:.3f} "
              f"FIT={r['fitness']:+.2f} corr={c:+.3f} {flag}  decay={r['settings']['decay']} "
              f"alpha={r['alpha_id']}\n      {r['optimized']}")
    print("=" * 100)
    json.dump(lowcorr, open(REPO / "WQ_LOWCORR_RESULTS.json", "w"), indent=2)
    print("wrote WQ_LOWCORR_RESULTS.json")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
