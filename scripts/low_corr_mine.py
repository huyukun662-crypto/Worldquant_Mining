"""Batch-7: mine NEW factors that are LOW-correlation to the existing champions.

The four factors found so far are all `reverse(ts_av_diff(close, W))` (close
mean-reversion) -- mutually highly correlated. To add diversification we mine
ORTHOGONAL signal families (volume, realized volatility [NOT IV], price-volume
correlation, intraday range, vwap dislocation, long-horizon momentum,
share-turnover, ts_rank) -- all fresh (no Alpha101/template reuse), no IV
fields, low-turnover structure (normalize wrapper + truncation=0.01).

Selection = submittable (SH>1.25, TO<0.25, all IS checks) AND low PnL
correlation to the champion rKomaon1 (|corr| of daily PnL < CORR_CEIL).

Run:  python scripts/low_corr_mine.py
"""

from __future__ import annotations

import importlib.util
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from mining_pipeline.wq_d1_pipeline import submit  # noqa: E402

VENDOR = REPO / "vendor" / "worldquant-miner"
CHAMPION = "rKomaon1"          # close mean-reversion W=14 decay=8
CORR_CEIL = 0.5               # keep candidates below this |corr| to champion

# Orthogonal families: (expression, decay). All operators verified accessible;
# no IV fields; normalize + trunc=0.01 keeps weight concentration in check.
FAMILIES = [
    ("normalize(reverse(ts_av_diff(volume, 20)))", 6),                       # volume reversion
    ("normalize(reverse(ts_std_dev(returns, 20)))", 6),                      # low realized-vol pref
    ("normalize(ts_corr(close, volume, 20))", 6),                           # price-volume corr
    ("normalize(reverse(ts_av_diff(divide(subtract(high, low), close), 20)))", 6),  # range reversion
    ("normalize(reverse(ts_av_diff(divide(close, vwap), 20)))", 6),          # vwap dislocation
    ("normalize(ts_delta(close, 60))", 6),                                  # long-horizon momentum
    ("normalize(reverse(ts_mean(divide(volume, sharesout), 20)))", 6),       # share-turnover (illiquidity)
    ("normalize(reverse(ts_rank(close, 20)))", 6),                          # ts_rank reversion
    ("normalize(reverse(ts_zscore(volume, 20)))", 6),                       # volume z-score reversion
    ("normalize(ts_regression(returns, ts_delay(returns, 1), 20))", 6),      # serial-dependence beta
]
BASE = {"universe": "TOP3000", "delay": 1, "neutralization": "SUBINDUSTRY",
        "truncation": 0.01, "pasteurization": "ON"}


def _load(p, name):
    spec = importlib.util.spec_from_file_location(name, p)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


def fetch_pnl(session, aid):
    """Return {date: daily_pnl} from the cumulative PnL recordset."""
    for _ in range(40):
        r = session.get(f"https://api.worldquantbrain.com/alphas/{aid}/recordsets/pnl",
                         timeout=30)
        ra = r.headers.get("Retry-After")
        if r.status_code == 200 and not ra:
            break
        if r.status_code not in (200, 202):
            return None
        time.sleep(float(ra) if ra else 1.0)
    recs = r.json().get("records", [])
    dates = [x[0] for x in recs]
    cum = np.array([float(x[1]) for x in recs])
    daily = np.diff(cum, prepend=cum[0] if len(cum) else 0.0)
    return dict(zip(dates, daily))


def corr(a: dict, b: dict) -> float:
    keys = sorted(set(a) & set(b))
    if len(keys) < 30:
        return float("nan")
    x = np.array([a[k] for k in keys]); y = np.array([b[k] for k in keys])
    if x.std() < 1e-12 or y.std() < 1e-12:
        return float("nan")
    return float(np.corrcoef(x, y)[0, 1])


def main():
    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        print("auth failed"); return 2
    print(f"authenticated as {cm.credentials.username}")

    champ_pnl = fetch_pnl(cm.session, CHAMPION)
    print(f"champion {CHAMPION} PnL days: {len(champ_pnl) if champ_pnl else 0}")

    print(f"running {len(FAMILIES)} orthogonal-family simulations (delay=1, no IV)")
    out = []
    for i, (expr, decay) in enumerate(FAMILIES, 1):
        s = dict(BASE); s["decay"] = decay
        print(f"[{i}/{len(FAMILIES)}] decay={decay} :: {expr}")
        res = submit(cm.session, expr, s)
        rec = asdict(res)
        if res.ok:
            c = float("nan")
            if res.alpha_id:
                pnl = fetch_pnl(cm.session, res.alpha_id)
                if pnl:
                    c = corr(pnl, champ_pnl)
            rec["corr_to_champion"] = c
            print(f"    SH={res.sharpe:+.3f} TO={res.turnover:.3f} DD={res.drawdown:.3f} "
                  f"FIT={res.fitness:+.2f} sub={res.submittable} "
                  f"corr_to_{CHAMPION}={c:+.3f} alpha={res.alpha_id}")
        else:
            rec["corr_to_champion"] = None
            print(f"    [{res.error[:90]}]")
        out.append(rec)
        with open(REPO / "WQ_MINING_REPORT_batch7.json", "w") as f:
            json.dump(out, f, indent=2)

    # Selection: submittable + low correlation
    good = [r for r in out if r["ok"] and r["submittable"]
            and r["sharpe"] > 1.25 and r["turnover"] < 0.25]
    lowcorr = [r for r in good if r["corr_to_champion"] is not None
               and abs(r["corr_to_champion"]) < CORR_CEIL]
    print("\n" + "=" * 100)
    print(f"submittable: {len(good)}   submittable & |corr|<{CORR_CEIL}: {len(lowcorr)}")
    for r in sorted(good, key=lambda r: abs(r.get("corr_to_champion") or 1)):
        c = r.get("corr_to_champion")
        flag = "LOW-CORR" if (c is not None and abs(c) < CORR_CEIL) else ""
        print(f"  SH={r['sharpe']:+.3f} TO={r['turnover']:.3f} DD={r['drawdown']:.3f} "
              f"FIT={r['fitness']:+.2f} corr={c:+.3f} {flag}  decay={r['settings']['decay']} "
              f"alpha={r['alpha_id']}\n      {r['optimized']}")
    print("=" * 100)
    json.dump(lowcorr, open(REPO / "WQ_LOWCORR_RESULTS.json", "w"), indent=2)
    print("wrote WQ_LOWCORR_RESULTS.json")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
