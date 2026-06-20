"""Batch-12: turn the new cross-sectional return-volume rank-spread structure
into a submittable factor. Batch-11 found
    normalize(subtract(rank(reverse(returns)), rank(ts_delta(volume, 5))))
at SH 1.40 / corr 0.387 but TO 0.55 & FIT 0.63. Cutting turnover (smooth the
returns leg + heavy decay) should also lift fitness. NO ts_av_diff, no IV."""
import importlib.util, json, sys
from dataclasses import asdict
from pathlib import Path
REPO=Path("/home/user/Worldquant_Mining"); sys.path.insert(0,str(REPO))
from mining_pipeline.wq_d1_pipeline import submit
from scripts.low_corr_mine import fetch_pnl, corr, CHAMPION
VENDOR=REPO/"vendor"/"worldquant-miner"
def _load(p,n):
    sp=importlib.util.spec_from_file_location(n,p); m=importlib.util.module_from_spec(sp); sp.loader.exec_module(m); return m
COMBOS=[
 ("normalize(subtract(rank(reverse(returns)), rank(ts_delta(volume, 5))))",32),
 ("normalize(subtract(rank(reverse(returns)), rank(ts_delta(volume, 5))))",64),
 ("normalize(subtract(rank(ts_mean(reverse(returns), 10)), rank(ts_delta(volume, 5))))",16),
 ("normalize(subtract(rank(ts_mean(reverse(returns), 10)), rank(ts_delta(volume, 5))))",32),
 ("normalize(subtract(rank(ts_mean(reverse(returns), 20)), rank(ts_delta(volume, 10))))",16),
 ("normalize(subtract(rank(ts_mean(reverse(returns), 20)), rank(ts_delta(volume, 10))))",32),
 ("normalize(subtract(rank(ts_decay_linear(reverse(returns), 10)), rank(ts_delta(volume, 5))))",16),
 ("normalize(subtract(rank(ts_mean(reverse(returns), 5)), rank(ts_mean(ts_delta(volume, 5), 5))))",16),
]
BASE={"universe":"TOP3000","delay":1,"neutralization":"SUBINDUSTRY","truncation":0.01,"pasteurization":"ON"}
cm=_load(VENDOR/"core"/"credential_manager.py","cm").CredentialManager(base_path=str(REPO))
cm.authenticate(auto_load=True,auto_prompt=False)
champ=fetch_pnl(cm.session,CHAMPION)
print(f"champion days {len(champ) if champ else 0}; running {len(COMBOS)} sims",flush=True)
out=[]
for i,(expr,decay) in enumerate(COMBOS,1):
    s=dict(BASE); s["decay"]=decay
    print(f"[{i}/{len(COMBOS)}] decay={decay} :: {expr}",flush=True)
    r=submit(cm.session,expr,s); rec=asdict(r)
    if r.ok:
        c=corr(fetch_pnl(cm.session,r.alpha_id) or {},champ) if r.alpha_id else float("nan")
        rec["corr_to_champion"]=c
        ok=r.submittable and r.sharpe>1.25 and r.turnover<0.25
        print(f"    SH={r.sharpe:+.3f} TO={r.turnover:.3f} DD={r.drawdown:.3f} FIT={r.fitness:+.2f} sub={r.submittable} corr={c:+.3f} alpha={r.alpha_id} {'<<< SUBMITTABLE'+(' LOW-CORR' if abs(c)<0.5 else '') if ok else ''}",flush=True)
    else:
        rec["corr_to_champion"]=None; print(f"    [{r.error[:90]}]",flush=True)
    out.append(rec); json.dump(out,open(REPO/"WQ_MINING_REPORT_batch12.json","w"),indent=2)
