"""Run a batch of (name, expression, settings) candidates concurrently on
WQ Brain, print IS metrics + checks, save JSON. delay=0 only.
"""
from __future__ import annotations
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.wq_lib import auth, simulate, is_metrics

# Candidate batches are defined inline; pass a batch name as argv[1].
def wrap_subind_value(field, n=120):
    # low-value long: industry-neutral, winsorized, backfilled
    return f"group_neutralize(-winsorize(ts_backfill({field}, {n}), std=4), subindustry)"

def wrap_subind_reversal(field, n=22):
    return f"group_neutralize(-winsorize(ts_backfill({field}, {n}), std=4), subindustry)"


BATCHES = {
    "news_probe": [
        ("pe_value",   "group_neutralize(-winsorize(ts_backfill(news_pe_ratio, 250), std=4), subindustry)", {"decay":6}),
        ("vol_shock",  "group_neutralize(-winsorize(ts_backfill(news_vol_stddev, 22), std=4), subindustry)", {"decay":6}),
        ("react_60m",  "group_neutralize(-winsorize(ts_backfill(news_pct_60min, 22), std=4), subindustry)", {"decay":6}),
        ("indx_rel",   "group_neutralize(-winsorize(ts_backfill(news_indx_perf, 22), std=4), subindustry)", {"decay":6}),
    ],
    # rel_* = supply-chain / competitor network (Cohen-Frazzini lead-lag).
    # cold (userCount 2-5), economically grounded -> low self-correlation.
    "rel_probe": [
        ("all_mom",   "group_neutralize(ts_decay_linear(ts_backfill(rel_ret_all, 60), 5), subindustry)", {"decay":4}),
        ("comp_mom",  "group_neutralize(ts_decay_linear(ts_backfill(rel_ret_comp, 60), 5), subindustry)", {"decay":4}),
        ("cust_mom",  "group_neutralize(ts_decay_linear(ts_backfill(rel_ret_cust, 120), 5), subindustry)", {"decay":4}),
        ("part_mom",  "group_neutralize(ts_decay_linear(ts_backfill(rel_ret_part, 120), 5), subindustry)", {"decay":4}),
    ],
    # analyst4 = cold consensus estimates (u<100). Forward value yields +
    # estimate-revision momentum. Neutralization via settings (SUBINDUSTRY).
    # Cold operators: ts_backfill + winsorize.
    "anl_probe": [
        ("fcf_yield",   "winsorize(ts_backfill(divide(est_fcf_ps, close), 120), std=4)", {"decay":4}),
        ("earn_yield",  "winsorize(ts_backfill(divide(est_epsr, close), 120), std=4)", {"decay":4}),
        ("book_price",  "winsorize(ts_backfill(divide(est_bookvalue_ps, close), 120), std=4)", {"decay":4}),
        ("fcf_assets",  "winsorize(ts_backfill(divide(est_fcf, est_tot_assets), 120), std=4)", {"decay":4}),
        ("eps_revis",   "winsorize(ts_backfill(divide(ts_delta(est_epsr, 66), close), 120), std=4)", {"decay":4}),
        ("ebitda_yield","winsorize(ts_backfill(divide(est_ebitda, cap), 120), std=4)", {"decay":4}),
    ],
}


def run_batch(batch_name, max_workers=3):
    cands = BATCHES[batch_name]
    session = auth()
    print(f"authenticated; running {len(cands)} candidates ({batch_name})")
    results = {}

    def task(item):
        name, expr, extra = item
        settings = {"delay": 0, "universe": "TOP3000", "neutralization": "SUBINDUSTRY"}
        settings.update(extra)
        r = simulate(session, expr, settings, verbose=False)
        return name, expr, r

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = [ex.submit(task, c) for c in cands]
        for fut in as_completed(futs):
            name, expr, r = fut.result()
            if r.get("ok"):
                m = is_metrics(r["alpha"])
                results[name] = {"expr": expr, "alpha_id": r["alpha_id"], "metrics": m, "settings": r["settings"]}
                ck = m["checks"]
                npass = sum(1 for v in ck.values() if v == "PASS")
                print(f"[{name:10}] SH={m['sharpe']!s:>6} TO={m['turnover']!s:>7} FIT={m['fitness']!s:>6} "
                      f"ret={m['returns']!s:>7} checks={npass}/{len(ck)} id={r['alpha_id']}")
                print(f"             checks={ck}")
            else:
                results[name] = {"expr": expr, "error": r.get("message") or r.get("body") or r.get("stage")}
                print(f"[{name:10}] ERR {r.get('stage')}: {(r.get('message') or r.get('body') or '')[:160]}")

    out = Path(__file__).resolve().parent.parent / f"probe_{batch_name}.json"
    json.dump(results, open(out, "w"), indent=2)
    print(f"wrote {out}")
    return results


if __name__ == "__main__":
    run_batch(sys.argv[1] if len(sys.argv) > 1 else "news_probe")
