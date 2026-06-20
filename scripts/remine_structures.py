"""Batch-11: re-mine with DIFFERENT structures (drop reverse(ts_av_diff(...))).

All four current submittable factors use normalize(reverse(ts_av_diff(price,W)))
-- the ts_av_diff mean-reversion structure. Per request we abandon that
structure entirely and explore 10 STRUCTURALLY-DISTINCT families (no ts_av_diff,
no IV fields), each fresh (no Alpha101/template reuse) and built only from
operators verified accessible. Low-turnover settings (normalize + trunc=0.01 +
decay). Reports submittable survivors (SH>1.25, TO<0.25, all IS checks) and
their PnL correlation to the existing champion rKomaon1.

Run:  python scripts/remine_structures.py
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

# (label, expression, decay) -- 10 distinct structures, NONE using ts_av_diff.
FAMILIES = [
    ("zscore-reversion",   "normalize(reverse(ts_zscore(close, 20)))", 16),
    ("tsrank-reversion",   "normalize(reverse(ts_rank(close, 20)))", 16),
    ("vol-norm-momentum",  "normalize(divide(ts_delta(close, 20), ts_std_dev(close, 20)))", 16),
    ("price-vol-corr",     "normalize(reverse(ts_corr(close, volume, 20)))", 16),
    ("xs-rank-reversal",   "normalize(reverse(rank(ts_delta(close, 5))))", 8),
    ("regression-resid",   "normalize(reverse(ts_regression(close, vwap, 20)))", 16),
    ("return-decay-rev",   "normalize(ts_decay_linear(reverse(returns), 20))", 8),
    ("range-zscore-rev",   "normalize(reverse(ts_zscore(divide(subtract(high, low), close), 20)))", 16),
    ("xs-ret-vol-spread",  "normalize(subtract(rank(reverse(returns)), rank(ts_delta(volume, 5))))", 8),
    ("scaled-tsdelta-rev", "normalize(reverse(ts_scale(ts_delta(close, 10), 20)))", 16),
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
    champ = fetch_pnl(cm.session, CHAMPION)
    print(f"champion {CHAMPION} PnL days: {len(champ) if champ else 0}")
    print(f"running {len(FAMILIES)} NEW-structure simulations (delay=1, no IV, no ts_av_diff)")

    out = []
    for i, (label, expr, decay) in enumerate(FAMILIES, 1):
        s = dict(BASE); s["decay"] = decay
        print(f"[{i}/{len(FAMILIES)}] {label} (decay={decay}) :: {expr}")
        res = submit(cm.session, expr, s)
        rec = asdict(res); rec["label"] = label
        if res.ok:
            c = corr(fetch_pnl(cm.session, res.alpha_id) or {}, champ) if res.alpha_id else float("nan")
            rec["corr_to_champion"] = c
            ok = res.submittable and res.sharpe > 1.25 and res.turnover < 0.25
            print(f"    SH={res.sharpe:+.3f} TO={res.turnover:.3f} DD={res.drawdown:.3f} "
                  f"FIT={res.fitness:+.2f} sub={res.submittable} corr={c:+.3f} "
                  f"alpha={res.alpha_id} {'<<< SUBMITTABLE' if ok else ''}")
        else:
            rec["corr_to_champion"] = None
            print(f"    [{res.error[:90]}]")
        out.append(rec)
        with open(REPO / "WQ_MINING_REPORT_batch11.json", "w") as f:
            json.dump(out, f, indent=2)

    good = [r for r in out if r["ok"] and r["submittable"]
            and r["sharpe"] > 1.25 and r["turnover"] < 0.25]
    print("\n" + "=" * 100)
    print(f"NEW-structure submittable factors: {len(good)}")
    for r in sorted(out, key=lambda r: -(r["sharpe"] if r["ok"] else -9)):
        if not r["ok"]:
            continue
        c = r.get("corr_to_champion")
        ok = r["submittable"] and r["sharpe"] > 1.25 and r["turnover"] < 0.25
        print(f"  [{r['label']:18}] SH={r['sharpe']:+.3f} TO={r['turnover']:.3f} "
              f"DD={r['drawdown']:.3f} FIT={r['fitness']:+.2f} corr={c:+.3f} "
              f"{'SUBMITTABLE ***' if ok else ''}  alpha={r['alpha_id']}")
    print("=" * 100)
    json.dump(good, open(REPO / "WQ_NEWSTRUCT_RESULTS.json", "w"), indent=2)
    print("wrote WQ_NEWSTRUCT_RESULTS.json")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
