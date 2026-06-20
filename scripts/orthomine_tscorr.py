"""Batch-13: mine ORTHOGONAL low-turnover factors from the price-volume
correlation structure (ts_corr) -- the most orthogonal lead from batch-11
(corr 0.10 to champion, TO 0.125). Turnover headroom is large, so use LOW
decay/short windows to lift Sharpe. NO ts_av_diff, no IV. Reports submittable
survivors and corr to champion rKomaon1."""
import importlib.util, json, sys
from dataclasses import asdict
from pathlib import Path
REPO=Path("/home/user/Worldquant_Mining"); sys.path.insert(0,str(REPO))
from mining_pipeline.wq_d1_pipeline import submit
from scripts.low_corr_mine import fetch_pnl, corr, CHAMPION
VENDOR=REPO/"vendor"/"worldquant-miner"
def _load(p,n):
    sp=importlib.util.spec_from_file_location(n,p); m=importlib.util.module_from_spec(sp); sp.loader.exec_module(m); return m
# (label, expr, decay) -- price-volume correlation variants, low decay
COMBOS=[
 ("pv-corr-w10-d4",   "normalize(reverse(ts_corr(close, volume, 10)))", 4),
 ("pv-corr-w5-d4",    "normalize(reverse(ts_corr(close, volume, 5)))", 4),
 ("pv-corr-w10-d0",   "normalize(reverse(ts_corr(close, volume, 10)))", 0),
 ("retvol-corr-w10",  "normalize(reverse(ts_corr(returns, volume, 10)))", 4),
 ("retvol-corr-w20",  "normalize(reverse(ts_corr(returns, volume, 20)))", 4),
 ("dpdv-corr-w10",    "normalize(reverse(ts_corr(ts_delta(close, 1), ts_delta(volume, 1), 10)))", 4),
 ("vwapvol-corr-w10", "normalize(reverse(ts_corr(vwap, volume, 10)))", 4),
 ("pv-adv-corr-w20",  "normalize(reverse(ts_corr(close, adv20, 20)))", 4),
 ("ret-autocorr-w20", "normalize(reverse(ts_corr(returns, ts_delay(returns, 1), 20)))", 4),
 ("retdv-corr-w10",   "normalize(reverse(ts_corr(returns, ts_delta(volume, 1), 10)))", 4),
]
BASE={"universe":"TOP3000","delay":1,"neutralization":"SUBINDUSTRY","truncation":0.01,"pasteurization":"ON"}
cm=_load(VENDOR/"core"/"credential_manager.py","cm").CredentialManager(base_path=str(REPO))
cm.authenticate(auto_load=True,auto_prompt=False)
champ=fetch_pnl(cm.session,CHAMPION)
print(f"champion days {len(champ) if champ else 0}; running {len(COMBOS)} orthogonal sims",flush=True)
out=[]
for i,(lab,expr,decay) in enumerate(COMBOS,1):
    s=dict(BASE); s["decay"]=decay
    print(f"[{i}/{len(COMBOS)}] {lab} (decay={decay}) :: {expr}",flush=True)
    r=submit(cm.session,expr,s); rec=asdict(r); rec["label"]=lab
    if r.ok:
        c=corr(fetch_pnl(cm.session,r.alpha_id) or {},champ) if r.alpha_id else float("nan")
        rec["corr_to_champion"]=c
        ok=r.submittable and r.sharpe>1.25 and r.turnover<0.25
        print(f"    SH={r.sharpe:+.3f} TO={r.turnover:.3f} DD={r.drawdown:.3f} FIT={r.fitness:+.2f} sub={r.submittable} corr={c:+.3f} alpha={r.alpha_id} {'<<< SUBMITTABLE'+(' LOW-CORR ***' if abs(c)<0.5 else '') if ok else ''}",flush=True)
    else:
        rec["corr_to_champion"]=None; print(f"    [{r.error[:90]}]",flush=True)
    out.append(rec); json.dump(out,open(REPO/"WQ_MINING_REPORT_batch13.json","w"),indent=2)
good=[r for r in out if r["ok"] and r["submittable"] and r["sharpe"]>1.25 and r["turnover"]<0.25]
print(f"\nsubmittable orthogonal: {len(good)}",flush=True)
json.dump(good,open(REPO/"WQ_ORTHO_RESULTS.json","w"),indent=2)
