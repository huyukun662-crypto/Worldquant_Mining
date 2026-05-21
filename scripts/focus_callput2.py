#!/usr/bin/env python3
"""Structural variants of the call-put IV-spread alpha to break the SH~2.0
single-leg ceiling while keeping the check-clearing zscore/scale wrap.

Single-leg ts_mean tops out at SH=1.97 with 6/8 (check-clearing), while
normalize+ts_decay_linear reaches SH=2.0 but fails CONCENTRATED_WEIGHT and
LOW_SUB_UNIVERSE_SHARPE. This sweeps NEW structures:
  - zscore/scale over ts_decay_linear (high-SH inner + check-clearing wrap)
  - cross-maturity skew (call_M1 - put_M2)
  - two-leg maturity blend
  - call/put ratio
  - ts_zscore inner normalization
at the check-clearing settings (SUBINDUSTRY, trunc 0.02, decay {3,4,5}).
"""

from __future__ import annotations
import argparse, itertools, json, logging, sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from mining_pipeline import wq_pipeline as wp

log = logging.getLogger("focus2")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

def cp(M):  # call-put spread at maturity M
    return f"subtract(implied_volatility_call_{M}, implied_volatility_put_{M})"
def cpx(M1, M2):  # cross-maturity
    return f"subtract(implied_volatility_call_{M1}, implied_volatility_put_{M2})"
def ratio(M):
    return f"divide(implied_volatility_call_{M}, implied_volatility_put_{M})"

def build_exprs():
    e = []
    for w in ("zscore", "scale"):
        for M in (180, 270, 360, 720):
            for W in (10, 15, 20):
                e.append(f"{w}(ts_decay_linear({cp(M)}, {W}))")
            e.append(f"{w}(ts_mean({ratio(M)}, 10))")
            e.append(f"{w}(ts_zscore({cp(M)}, 60))")
        # cross-maturity skew
        e.append(f"{w}(ts_mean({cpx(360,180)}, 10))")
        e.append(f"{w}(ts_mean({cpx(720,360)}, 10))")
        e.append(f"{w}(ts_mean({cpx(720,180)}, 10))")
        # two-leg blend
        e.append(f"{w}(add(ts_mean({cp(360)}, 10), ts_mean({cp(180)}, 10)))")
        e.append(f"{w}(add(ts_mean({cp(720)}, 10), ts_mean({cp(360)}, 10)))")
    # dedup preserve order
    seen=set(); out=[]
    for x in e:
        if x in seen: continue
        seen.add(x); out.append(x)
    return out

_SIG = ("universe","delay","decay","truncation","neutralization")
def sig(expr,s): return expr+"|"+"|".join(f"{k}={s.get(k)}" for k in _SIG)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="WQ_D0_CALLPUT_FOCUS2.json")
    ap.add_argument("--archives", nargs="*",
                    default=["WQ_D0_EVOLVE_REPORT.json", "WQ_D0_CALLPUT_FOCUS.json"])
    ap.add_argument("--decays", nargs="*", type=int, default=[3,4,5])
    ap.add_argument("--max", type=int, default=120)
    args = ap.parse_args()

    cm_mod = wp._load(wp.VENDOR/"core"/"credential_manager.py","cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("auth failed"); return 2
    log.info(f"auth {cm.credentials.username}")

    done=set()
    for p in args.archives:
        fp=REPO/p
        if fp.exists():
            try:
                for d in json.load(open(fp)):
                    if d.get("ok"): done.add(sig(d["expression"], d["settings"]))
            except Exception: pass
    log.info(f"{len(done)} already evaluated")

    results=[]
    if (REPO/args.out).exists():
        try: results=json.load(open(REPO/args.out))
        except Exception: results=[]

    exprs = build_exprs()
    log.info(f"{len(exprs)} structural variants x {len(args.decays)} decays")
    n=0
    for expr, decay in itertools.product(exprs, args.decays):
        if n>=args.max: break
        s={"universe":"TOP3000","delay":0,"decay":decay,"truncation":0.02,
           "neutralization":"SUBINDUSTRY","pasteurization":"ON"}
        if sig(expr,s) in done: continue
        n+=1
        log.info(f"[{n}] d{decay} {expr[:70]}")
        res=wp.submit(cm.session, expr, s)
        if not res.ok:
            log.info(f"   ERR {res.error[:70]}"); continue
        fails=[]
        try:
            ra=cm.session.get(f"https://api.worldquantbrain.com/alphas/{res.alpha_id}",timeout=30)
            fails=[c["name"] for c in ((ra.json().get("is") or {}).get("checks") or []) if c.get("result")=="FAIL"]
        except Exception: pass
        rec={"ok":True,"alpha_id":res.alpha_id,"expression":expr,"settings":s,
             "sharpe":res.sharpe,"turnover":res.turnover,"fitness":res.fitness,
             "checks_passed":res.checks_passed,"checks_total":res.checks_total,"fails":fails}
        results.append(rec)
        json.dump(results, open(REPO/args.out,"w"), indent=2)
        full = res.sharpe>=2.0 and res.fitness>=1.3 and res.turnover<0.25 and not fails
        log.info(f"   SH={res.sharpe:+.3f} TO={res.turnover:.3f} FIT={res.fitness:+.3f} "
                 f"chk={res.checks_passed}/{res.checks_total} fails={fails}"
                 f"{'  <<< FULL PASS' if full else ''}")

    full=[r for r in results if r['sharpe']>=2.0 and r['fitness']>=1.3 and r['turnover']<0.25 and not r['fails']]
    print("="*100)
    print(f"submitted {n}; results {len(results)}; FULL-PASS {len(full)}")
    for r in sorted(full,key=lambda x:-x['sharpe']):
        print(f"  SH={r['sharpe']:.2f} TO={r['turnover']:.3f} FIT={r['fitness']:.2f} {r['alpha_id']}  {r['expression']}")
    return 0

if __name__=="__main__":
    sys.exit(main() or 0)
