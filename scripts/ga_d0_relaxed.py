"""GA v2: evolve a SIMPLE, REGULARIZED, ECONOMICALLY-MEANINGFUL D0 non-IV
factor that is UNCORRELATED with the existing reversal+quality composite.

Differences vs ga_d0.py:
  - K in {1,2} only (simple).
  - Interpretable operators only (no signed_power/scale/nested decay).
  - Seeded with CLASSIC economic anomalies (low-vol, momentum, value,
    profitability, illiquidity, size, cashflow-yield, investment).
  - REGULARIZED fitness: penalize complexity (#terms, op depth) AND reward
    low |self_corr| (uncorrelated w/ existing pool). self_corr is the WQ
    correlation vs the user's submitted alphas.
  - STOP = submittable (no FAIL check) AND |self_corr|<0.5 (uncorrelated).
NO implied_volatility / option fields. delay=0.
"""
from __future__ import annotations
import json, sys, random, hashlib
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mine_cold_fields import (submit, fetch_self_corr, _load, VENDOR, REPO, log)

PV   = ["close","open","high","low","volume","vwap","returns","cap","adv20"]
FUND = ["assets","equity","ebit","ebitda","sales","cogs","capex","bookvalue_ps",
        "cashflow_op","debt","cash"]
TSOPS  = ["id","zscore","mean","delta","std","sum","rank","decay"]
GROUPS = ["gr_sub","gr_mkt","rank"]                              # readable neut ranks
WINDOWS= [20,60,120,250]
WEIGHTS= [0.5,1.0]
SIGNS  = [-1.0,1.0]
NEUT   = ["MARKET","SUBINDUSTRY"]
DECAY  = [0,4,8]
TRUNC  = [0.05,0.08]
KS     = [2,2,3]                                                 # allow pairing (option 2)

def fld(f): return f"ts_backfill({f},250)" if f in FUND else f
def render_ratio(t):
    n=fld(t["num"])
    if t.get("den") and t["den"]!=t["num"]: return f"divide({n},{fld(t['den'])})"
    return n
def render_tsop(x,op,w):
    return {"id":x,"zscore":f"ts_zscore({x},{w})","mean":f"ts_mean({x},{w})",
            "delta":f"ts_delta({x},{w})","std":f"ts_std_dev({x},{w})",
            "sum":f"ts_sum({x},{w})","rank":f"ts_rank({x},{w})",
            "decay":f"ts_decay_linear({x},{w})"}[op]
def render_group(x,g):
    return {"gr_sub":f"group_rank({x},subindustry)","gr_mkt":f"group_rank({x},market)",
            "rank":f"rank({x})"}[g]
def render_term(t): return render_group(render_tsop(render_ratio(t),t["op"],t["w"]),t["grp"])
def render(g):
    e="".join(f"{t['sign']*t['weight']:+g}*{render_term(t)}" for t in g["terms"])
    return e[1:] if e.startswith("+") else e
def settings(g): return {"delay":0,"universe":"TOP3000","decay":g["decay"],
                          "truncation":g["trunc"],"neutralization":g["neut"]}
def complexity(g):
    nops=sum(1 for t in g["terms"] if t["op"]!="id")+sum(1 for t in g["terms"] if t.get("den"))
    return (len(g["terms"])-1) + 0.5*nops          # K=1, no-op, no-ratio => 0

# classic economic-anomaly seeds (each 1 simple interpretable term)
def T(num,den=None,op="id",w=60,grp="gr_sub",sign=1.0,wt=1.0):
    return {"num":num,"den":den,"op":op,"w":w,"grp":grp,"sign":sign,"weight":wt}
def g1(terms,neut="SUBINDUSTRY",dec=4,tr=0.05): return {"terms":terms,"neut":neut,"decay":dec,"trunc":tr}
SEEDS=[
 ("gp_x_mom",   g1([T("sales","assets"),T("returns",op="sum",w=250,sign=1.0,wt=0.5)])),
 ("gp_x_lowvol",g1([T("sales","assets"),T("returns",op="std",w=60,sign=-1.0,wt=0.5)])),
 ("gp_x_strev", g1([T("sales","assets"),T("returns",op="sum",w=20,sign=-1.0,wt=0.5)])),
 ("gp_x_illiq", g1([T("sales","assets"),T("returns",den="volume",op="std",w=20,sign=1.0,wt=0.5)])),
 ("gp_x_cf",    g1([T("sales","assets"),T("cashflow_op","assets",wt=0.5)])),
 ("ebit_x_mom", g1([T("ebit","assets"),T("returns",op="sum",w=250,sign=1.0,wt=0.5)])),
 ("gp_solo_dec",g1([T("sales","assets",op="mean",w=20)],dec=8)),
 ("gp_x_invest",g1([T("sales","assets"),T("assets",op="delta",w=250,sign=-1.0,wt=0.5)])),
]
def rand_term():
    ratio=random.random()<0.4
    num=random.choice(PV+FUND); den=random.choice(FUND) if ratio else None
    if ratio and random.random()<0.4: num,den=random.choice(PV),random.choice(["vwap","close","volume"])
    return {"num":num,"den":den,"op":random.choice(TSOPS),"w":random.choice(WINDOWS),
            "grp":random.choice(GROUPS),"sign":random.choice(SIGNS),"weight":random.choice(WEIGHTS)}
def rand_genome():
    return {"terms":[rand_term() for _ in range(random.choice(KS))],
            "neut":random.choice(NEUT),"decay":random.choice(DECAY),"trunc":random.choice(TRUNC)}
def mutate(g):
    g=json.loads(json.dumps(g)); r=random.random()
    if r<0.55:
        t=random.choice(g["terms"]); k=random.choice(["num","den","op","w","grp","sign","weight"])
        if k=="num": t["num"]=random.choice(PV+FUND)
        elif k=="den": t["den"]=random.choice([None,None]+FUND)
        elif k=="op": t["op"]=random.choice(TSOPS)
        elif k=="w": t["w"]=random.choice(WINDOWS)
        elif k=="grp": t["grp"]=random.choice(GROUPS)
        elif k=="sign": t["sign"]*=-1
        else: t["weight"]=random.choice(WEIGHTS)
    elif r<0.8:
        k=random.choice(["neut","decay","trunc"]); g[k]=random.choice({"neut":NEUT,"decay":DECAY,"trunc":TRUNC}[k])
    elif len(g["terms"])<2: g["terms"].append(rand_term())
    elif len(g["terms"])>1: g["terms"].pop(random.randrange(len(g["terms"])))
    return g
def crossover(a,b):
    c=json.loads(json.dumps(a)); pool=a["terms"]+b["terms"]
    c["terms"]=random.sample(pool,min(random.choice(KS),len(pool)))
    for k in ["neut","decay","trunc"]: c[k]=random.choice([a[k],b[k]])
    return c
def ghash(g): return hashlib.md5(render(g).encode()).hexdigest()[:10]

LAMBDA=0.12  # relaxed regularization (option 2)
def fitness(r,g):
    if not r or not r.ok: return -9.0, False
    hard=[c for c in r.checks if c.get("result")=="FAIL"]
    sc=r.self_corr
    submit_ok=(len(hard)==0) and (sc is None or abs(sc)<0.6)   # submittable AND uncorrelated(relaxed)
    f=r.sharpe+0.5*r.fitness - LAMBDA*complexity(g)            # regularization
    if r.turnover>0.30: f-=(r.turnover-0.30)*3.0
    if sc is not None:                                         # reward uncorrelated, punish correlated
        if abs(sc)<0.3: f+=0.4
        elif abs(sc)>0.5: f-=2.0*(abs(sc)-0.5)
    for c in hard:
        if c.get("name") not in ("LOW_SHARPE","LOW_FITNESS"): f-=0.5
    return f, submit_ok

def main():
    seed=int(sys.argv[sys.argv.index("--seed")+1]) if "--seed" in sys.argv else 11
    POP=int(sys.argv[sys.argv.index("--pop")+1]) if "--pop" in sys.argv else 12
    GENS=int(sys.argv[sys.argv.index("--gens")+1]) if "--gens" in sys.argv else 10
    random.seed(seed)
    cm_mod=_load(VENDOR/"core"/"credential_manager.py","cm")
    cm=cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True,auto_prompt=False): return 2
    log.info(f"auth {cm.credentials.username}  GAv3(relaxed/pairing/uncorr) seed={seed} pop={POP} gens={GENS}")
    out=REPO/"WQ_GA_D0_RELAXED.json"; cache={}; hall=[]
    # resume: reload previously-evaluated genomes so a crash doesn't lose progress
    if out.exists():
        try:
            prev=json.load(open(out))
            for r in prev.get("hall",[]):
                if r.get("hash"): cache[r["hash"]]=r; hall.append(r)
            hall.sort(key=lambda x:x["fit"],reverse=True)
            log.info(f"resumed {len(cache)} cached evaluations from {out.name}")
        except Exception as e: log.warning(f"resume failed: {e}")
    def evaluate(g,label=""):
        try: h=ghash(g); expr=render(g)
        except Exception as e:   # invalid genome render -> kill it, never crash the GA
            log.warning(f"   render-err (bad genome): {str(e)[:60]}")
            return {"hash":"badgen","label":label,"expr":"","settings":{},"genome":g,
                    "fit":-9.0,"submit_ok":False,"complexity":99,"ok":False,
                    "sharpe":None,"turnover":None,"fitness":None,"self_corr":None,
                    "alpha_id":None,"fails":[],"err":"render-err"}
        if h in cache: return cache[h]
        # robust to flaky WQ network (SSL/ReadTimeout/conn errors): retry then skip
        r=None
        for attempt in range(3):
            try:
                r=submit(cm.session,f"gas_{h}",expr,settings(g))
                if r.ok:
                    try: sc,_,_=fetch_self_corr(cm.session,r.alpha_id,timeout_s=90); r.self_corr=sc
                    except Exception as e: log.warning(f"   [{h}] self_corr net-err: {str(e)[:60]}"); r.self_corr=None
                break
            except Exception as e:
                log.warning(f"   [{h}] submit net-err (try {attempt+1}/3): {str(e)[:70]}")
                import time as _t; _t.sleep(20)
        if r is None:   # persistent network failure: skip WITHOUT caching (retry in later gen)
            return {"hash":h,"label":label,"expr":expr,"settings":settings(g),"genome":g,
                    "fit":-9.0,"submit_ok":False,"complexity":complexity(g),"ok":False,
                    "sharpe":None,"turnover":None,"fitness":None,"self_corr":None,
                    "alpha_id":None,"fails":[],"err":"net-skip"}
        fit,ok=fitness(r,g)
        rec={"hash":h,"label":label,"expr":expr,"settings":settings(g),"genome":g,
             "fit":fit,"submit_ok":ok,"complexity":complexity(g),"ok":r.ok,
             "sharpe":getattr(r,"sharpe",None),"turnover":getattr(r,"turnover",None),
             "fitness":getattr(r,"fitness",None),"self_corr":getattr(r,"self_corr",None),
             "alpha_id":getattr(r,"alpha_id",None),
             "fails":[c.get("name") for c in getattr(r,"checks",[]) if c.get("result")=="FAIL"],
             "err":getattr(r,"error",None)}
        cache[h]=rec; hall.append(rec); hall.sort(key=lambda x:x["fit"],reverse=True)
        json.dump({"hall":hall[:40],"n_eval":len(cache)},open(out,"w"),indent=2)
        flag=" *** SUBMIT+UNCORR ***" if ok else ""
        if r.ok: log.info(f"   [{h}]{(' '+label) if label else ''} fit={fit:+.3f} SH={r.sharpe:+.3f} TO={r.turnover:.3f} FIT={r.fitness:+.3f} sc={r.self_corr} cx={complexity(g):.1f} fails={rec['fails']}{flag}")
        else: log.info(f"   [{h}]{(' '+label) if label else ''} FAILED: {str(r.error)[:80]}")
        return rec
    # gen 0 = economic-anomaly seeds
    log.info("=== generation 1/%d (economic-anomaly seeds + random) ==="%GENS)
    pop=[]
    for name,g in SEEDS:
        rec=evaluate(g,label=name)
        if rec["submit_ok"]:
            log.info(f"!!! SUBMITTABLE+UNCORR seed [{rec['hash']}] {name} {rec['alpha_id']}")
            json.dump({"winner":rec,"hall":hall[:40]},open(out,"w"),indent=2)
            print(f"\n*** WINNER (seed {name}): {rec['alpha_id']} SH={rec['sharpe']} FIT={rec['fitness']} sc={rec['self_corr']}\n{rec['expr']}\n{rec['settings']}")
            return 0
        pop.append(g)
    pop+=[rand_genome() for _ in range(max(0,POP-len(pop)))]
    pop=pop[:max(POP,len(SEEDS))]
    for gen in range(2,GENS+1):
        scored=[(evaluate(g)["fit"], g) for g in pop]   # evaluate() is cache-aware + net-robust
        scored.sort(key=lambda x:x[0],reverse=True)
        b=cache.get(ghash(scored[0][1])) or evaluate(scored[0][1])
        log.info(f"   gen{gen-1} best fit={scored[0][0]:+.3f} SH={b['sharpe']} sc={b['self_corr']} cx={b['complexity']:.1f} [{b['hash']}] {b.get('label','')}")
        log.info(f"=== generation {gen}/{GENS} ===")
        elite=[g for _,g in scored[:3]]; newpop=list(elite)
        def tourn():
            c=random.sample(scored,min(3,len(scored))); c.sort(key=lambda x:x[0],reverse=True); return c[0][1]
        while len(newpop)<POP:
            child=crossover(tourn(),tourn()) if random.random()<0.5 else json.loads(json.dumps(tourn()))
            child=mutate(child)
            newpop.append(child)
        pop=newpop
        for g in pop:
            rec=evaluate(g)
            if rec["submit_ok"]:
                log.info(f"!!! SUBMITTABLE+UNCORR gen{gen} [{rec['hash']}] {rec['alpha_id']}")
                json.dump({"winner":rec,"hall":sorted(hall,key=lambda x:x['fit'],reverse=True)[:40]},open(out,"w"),indent=2)
                print(f"\n*** WINNER: {rec['alpha_id']} SH={rec['sharpe']} FIT={rec['fitness']} sc={rec['self_corr']}\n{rec['expr']}\n{rec['settings']}")
                return 0
    hall.sort(key=lambda x:x["fit"],reverse=True)
    print("\n"+"="*110); print(f"GAv2 done, no submit+uncorr winner. Top by regularized fitness ({len(cache)} evals):")
    for r in hall[:12]:
        print(f"  fit={r['fit']:+.3f} SH={r['sharpe']} TO={r['turnover']} FIT={r['fitness']} sc={r['self_corr']} cx={r['complexity']:.1f} fails={r['fails']} [{r['hash']}] {r.get('label','')}")
        print(f"      {r['expr']}")
    print("="*110)
    return 0
if __name__=="__main__": sys.exit(main() or 0)
