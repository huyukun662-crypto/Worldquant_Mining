"""Decorrelate a Category-一 alpha (passes all IS checks, fails only
SELF_CORRELATION) by blending it with an orthogonal overlay signal, then
verify the blend still passes IS checks AND has lower PnL correlation to a
reference pool.

self-correlation is measured at WQ submit-time against the user's full pool,
which we cannot query directly. As a proxy we correlate the blend's daily
PnL against the PnL of the alphas in the tuning-queue pool (the cluster the
base alpha is over-correlated with). A blend that keeps every IS check PASS
and drops max |corr| below ~0.6-0.7 is the decorrelation candidate.

Usage:
    python scripts/decorrelate.py --base-id xAmpqQpw \
        --queue TUNE_QUEUE_alpha.txt --out DECORR_RESULTS.json
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import time
from pathlib import Path

import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("decorr")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"
import sys
sys.path.insert(0, str(REPO))
from mining_pipeline.agent_workflow import SimulatorAgent  # noqa: E402
from scripts.tune_queue import parse_queue  # noqa: E402

# Orthogonal overlays (not in the user's pool): close-loc-in-range reversal
# (orthogonal to leverage), long seasonality, and asset-turnover quality.
OVERLAYS = {
    "clr_reversal": "reverse(rank(ts_decay_linear(divide(subtract(close, low), subtract(high, low)), 8)))",
    "seasonality":  "rank(ts_delta(close, 240))",
    "asset_turn":   "rank(divide(sales, assets))",
}


def _load(p, name):
    spec = importlib.util.spec_from_file_location(name, p)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


def fetch_pnl(session, aid, tries=10):
    url = f"https://api.worldquantbrain.com/alphas/{aid}/recordsets/pnl"
    for _ in range(tries):
        try:
            r = session.get(url, timeout=30)
        except Exception:
            time.sleep(5); continue
        if r.status_code == 429:
            time.sleep(15); continue
        if r.status_code == 200 and r.text.strip():
            recs = r.json().get("records") or []
            if not recs:
                return None
            c = np.array([float(x[1]) for x in recs])
            return dict(zip([x[0] for x in recs], np.diff(c, prepend=c[0])))
        time.sleep(4)
    return None


def corr(a, b):
    k = sorted(set(a) & set(b))
    if len(k) < 60:
        return 0.0
    x = np.array([a[d] for d in k]); y = np.array([b[d] for d in k])
    return float(np.corrcoef(x, y)[0, 1]) if x.std() > 1e-12 and y.std() > 1e-12 else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-id", required=True)
    ap.add_argument("--queue", default="TUNE_QUEUE_alpha.txt")
    ap.add_argument("--weights", default="0.7,0.6,0.5")
    ap.add_argument("--out", default="DECORR_RESULTS.json")
    args = ap.parse_args()

    alphas = {a["alpha_id"]: a for a in parse_queue(Path(args.queue))}
    base = alphas[args.base_id]
    bexpr, bset = base["expression"], base["base"]
    settings = {"universe": bset["universe"], "delay": bset["delay"],
                "decay": bset["decay"], "neutralization": bset["neutralization"],
                "truncation": bset["truncation"], "pasteurization": "ON"}
    log.info(f"base {args.base_id}: {bexpr[:80]}")
    log.info(f"base settings: {settings}")

    cm = _load(VENDOR / "core" / "credential_manager.py", "cm").CredentialManager(base_path=str(REPO))
    cm.authenticate(auto_load=True, auto_prompt=False)
    sim = SimulatorAgent(cm.session)

    # pool PnL = all queue alphas except the base itself (the cluster it
    # over-correlates with). fetch lazily.
    pool_ids = [aid for aid in alphas if aid != args.base_id]
    pool_pnl = {}
    for aid in pool_ids:
        p = fetch_pnl(cm.session, aid)
        if p:
            pool_pnl[aid] = p
        time.sleep(0.2)
    log.info(f"fetched PnL for {len(pool_pnl)}/{len(pool_ids)} pool alphas")

    def maxcorr(pnl):
        cs = [(abs(corr(pnl, p)), aid) for aid, p in pool_pnl.items()]
        return max(cs) if cs else (0.0, "-")

    results = []
    # baseline: the original alpha's correlation to the pool
    weights = [float(w) for w in args.weights.split(",")]
    for ov_name, ov_expr in OVERLAYS.items():
        for w in weights:
            blend = (f"add(multiply({w:.2f}, zscore({bexpr})), "
                     f"multiply({1-w:.2f}, zscore({ov_expr})))")
            log.info(f"blend {ov_name} w={w:.2f} ...")
            res = sim.submit(blend, settings)
            if not res.ok:
                log.info(f"   [{res.error[:70]}]"); continue
            fails = [c["name"] for c in res.checks
                     if c.get("result") not in ("PASS", "PENDING")]
            pnl = fetch_pnl(cm.session, res.alpha_id)
            mc, mcw = maxcorr(pnl) if pnl else (None, None)
            rec = {"overlay": ov_name, "weight": w, "alpha_id": res.alpha_id,
                   "sharpe": res.sharpe, "turnover": res.turnover,
                   "fitness": res.fitness, "drawdown": res.drawdown,
                   "is_fails": fails, "is_submittable": res.submittable,
                   "max_pool_corr": round(mc, 3) if mc is not None else None,
                   "max_corr_with": mcw, "expression": blend, "settings": res.settings}
            results.append(rec)
            log.info(f"   SH={res.sharpe:+.2f} FIT={res.fitness:+.2f} "
                     f"IS_pass={not fails} fails={fails} maxPoolCorr={rec['max_pool_corr']}")
            json.dump(results, open(args.out, "w"), indent=2)

    print("\n" + "=" * 100)
    print(f"base {args.base_id} decorrelation blends (want IS_pass=True AND low max_pool_corr):\n")
    print(f"{'overlay':<14}{'w':>5}{'SH':>6}{'FIT':>6}{'IS?':>5}{'maxCorr':>9}  fails")
    for r in sorted(results, key=lambda r: (not r["is_fails"], -(r["max_pool_corr"] or 1)), reverse=True):
        print(f"{r['overlay']:<14}{r['weight']:>5.2f}{r['sharpe']:>6.2f}{r['fitness']:>6.2f}"
              f"{'YES' if not r['is_fails'] else 'no':>5}{(r['max_pool_corr'] or 0):>9.2f}  {r['is_fails']}")
    print("=" * 100)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
