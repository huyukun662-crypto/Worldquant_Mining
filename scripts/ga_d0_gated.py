"""GA v4: replicate the IV-winner STRUCTURE with NON-IV scores.

The D0+IV factors that crushed the bar all shared one structure:
  score = quantile(<directional signal>);
  gate  = (no_extreme_jump) AND (event-day shock: news_pct or volume);
  trade_when(gate, ts_decay_linear(signed_power(score-0.5, p), 5), -1)

That sparse-gate / high-conviction / amplified-around-0.5 pattern is
WHY it cleared D0. The score doesn't have to be IV -- any directional
signal that's strong on shock days could work. GA v4 evolves over:
  - non-IV score components (K=1-2 fields/ratios with cross-sectional rank)
  - gate variable (news shock or volume spike)
  - gate threshold (sparseness 0.55-0.90)
  - signed_power exponent (2-5)
  - decay (3-8), truncation (0.02-0.10), neutralization (SUB/MKT/IND)
Stop: no FAIL check. delay=0, NO option/IV fields anywhere.
"""
from __future__ import annotations
import json, sys, random, hashlib
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mine_cold_fields import (submit, fetch_self_corr, _load, VENDOR, REPO, log)

PV   = ["close","open","high","low","volume","vwap","returns","cap","adv20"]
FUND = ["assets","equity","ebit","ebitda","sales","cogs","capex","bookvalue_ps",
        "cashflow_op","debt","cash"]
TSOPS=["id","zscore","mean","sum","delta","std","rank"]
WINDOWS=[5,10,20,60,120,250]
SIGNS=[-1.0,1.0]
WEIGHTS=[0.5,1.0]
GATES = {                # gate-variable choices (all non-IV)
 "news_strong": lambda th: f"(ts_backfill(news_pct_90min,5)<1)*(ts_rank(abs(news_pct_30min),60)>{th})",
 "news_pos":    lambda th: f"(ts_backfill(news_pct_90min,5)<1)*(ts_rank(news_pct_30min,60)>{th})",
 "vol_spike":   lambda th: f"(ts_rank(volume,20)>{th})",
 "vol_adv":     lambda th: f"(ts_rank(divide(volume,adv20),20)>{th})",
 "abs_ret":     lambda th: f"(ts_rank(abs(returns),60)>{th})",
}
THRESH=[0.55,0.65,0.75,0.85,0.92]
AMPS=[2,3,4,5]
DECAYS=[3,4,6,8]
TRUNCS=[0.02,0.04,0.06,0.08]
NEUTS=["SUBINDUSTRY","MARKET","INDUSTRY"]
KS=[1,1,2]

def fld(f): return f"ts_backfill({f},250)" if f in FUND else f
def render_ratio(t):
    n=fld(t["num"])
    if t.get("den") and t["den"]!=t["num"]: return f"divide({n},{fld(t['den'])})"
    return n
def render_tsop(x,op,w):
    return {"id":x,"zscore":f"ts_zscore({x},{w})","mean":f"ts_mean({x},{w})",
            "delta":f"ts_delta({x},{w})","std":f"ts_std_dev({x},{w})",
            "sum":f"ts_sum({x},{w})","rank":f"ts_rank({x},{w})"}[op]
def render_term(t): return render_tsop(render_ratio(t),t["op"],t["w"])
def render(g):
    score_inner="".join(f"{t['sign']*t['weight']:+g}*group_rank({render_term(t)},subindustry)" for t in g["terms"])
    if score_inner.startswith("+"): score_inner=score_inner[1:]
    score=f"quantile({score_inner})"
    gate=GATES[g["gate_var"]](g["threshold"])
    return (f"score={score};\n"
            f"gate={gate};\n"
            f"trade_when(gate, ts_decay_linear(signed_power(score-0.5,{g['amp']}),5), -1)")
def settings(g): return {"delay":0,"universe":"TOP3000","decay":g["decay"],
                          "truncation":g["trunc"],"neutralization":g["neut"]}
def complexity(g): return (len(g["terms"])-1) + 0.3*sum(1 for t in g["terms"] if t.get("den")) + 0.1*(g["amp"]-2)
def ghash(g):
    try: return hashlib.md5(render(g).encode()).hexdigest()[:10]
    except Exception: return "bad"+hashlib.md5(str(g).encode()).hexdigest()[:7]

def T(num,den=None,op="id",w=20,sign=1.0,wt=1.0):
    return {"num":num,"den":den,"op":op,"w":w,"sign":sign,"weight":wt}
def G(terms,gv="news_strong",th=0.55,amp=3,neut="SUBINDUSTRY",dec=4,tr=0.02):
    return {"terms":terms,"gate_var":gv,"threshold":th,"amp":amp,"neut":neut,"decay":dec,"trunc":tr}
SEEDS=[
 ("gp_gate_news",  G([T("sales","assets")])),
 ("gp_gate_vol",   G([T("sales","assets")],gv="vol_spike",th=0.85)),
 ("gp_gate_absret",G([T("sales","assets")],gv="abs_ret",th=0.75)),
 ("rev_gate_news", G([T("returns",op="sum",w=5,sign=-1.0)])),
 ("rev_capex_gate",G([T("returns",op="sum",w=5,sign=-1.0),T("capex","assets",wt=0.5)])),
 ("zrev_gate",     G([T("close",op="zscore",w=20,sign=-1.0)])),
 ("ebit_gate",     G([T("ebit","assets")])),
 ("vwap_dev_gate", G([T("close",den="vwap",sign=-1.0)],gv="vol_spike",th=0.85)),
 ("mom_gate",      G([T("returns",op="sum",w=60)],gv="abs_ret",th=0.75)),
 ("cf_gate_news",  G([T("cashflow_op","assets")])),
 ("vol_x_rev",     G([T("returns",op="sum",w=5,sign=-1.0)],gv="vol_adv",th=0.85,amp=4)),
 ("gp_gate_p5",    G([T("sales","assets")],amp=5,th=0.75)),
]

def rand_term():
    ratio=random.random()<0.4
    num=random.choice(PV+FUND); den=random.choice(FUND) if ratio else None
    if ratio and random.random()<0.4: num,den=random.choice(PV),random.choice(["vwap","close","volume","open"])
    return {"num":num,"den":den,"op":random.choice(TSOPS),"w":random.choice(WINDOWS),
            "sign":random.choice(SIGNS),"weight":random.choice(WEIGHTS)}
def rand_genome():
    return {"terms":[rand_term() for _ in range(random.choice(KS))],
            "gate_var":random.choice(list(GATES.keys())),"threshold":random.choice(THRESH),
            "amp":random.choice(AMPS),"neut":random.choice(NEUTS),
            "decay":random.choice(DECAYS),"trunc":random.choice(TRUNCS)}
def mutate(g):
    g=json.loads(json.dumps(g)); r=random.random()
    if r<0.5:
        t=random.choice(g["terms"]); k=random.choice(["num","den","op","w","sign","weight"])
        if k=="num": t["num"]=random.choice(PV+FUND)
        elif k=="den": t["den"]=random.choice([None,None]+FUND)
        elif k=="op": t["op"]=random.choice(TSOPS)
        elif k=="w": t["w"]=random.choice(WINDOWS)
        elif k=="sign": t["sign"]*=-1
        else: t["weight"]=random.choice(WEIGHTS)
    elif r<0.85:
        k=random.choice(["gate_var","threshold","amp","neut","decay","trunc"])
        g[k]=random.choice({"gate_var":list(GATES.keys()),"threshold":THRESH,"amp":AMPS,
                            "neut":NEUTS,"decay":DECAYS,"trunc":TRUNCS}[k])
    elif len(g["terms"])<2: g["terms"].append(rand_term())
    elif len(g["terms"])>1: g["terms"].pop(random.randrange(len(g["terms"])))
    return g
def crossover(a,b):
    c=json.loads(json.dumps(a)); pool=a["terms"]+b["terms"]
    c["terms"]=random.sample(pool,min(random.choice(KS),len(pool)))
    for k in ["gate_var","threshold","amp","neut","decay","trunc"]:
        c[k]=random.choice([a[k],b[k]])
    return c

LAMBDA=0.1
def fitness(r,g):
    if not r or not r.ok: return -9.0, False
    hard=[c for c in r.checks if c.get("result")=="FAIL"]
    submit_ok=(len(hard)==0) and (r.self_corr is None or abs(r.self_corr)<0.7)
    f=r.sharpe + 0.6*r.fitness - LAMBDA*complexity(g)
    if r.turnover>0.30: f-=(r.turnover-0.30)*3.0
    return f, submit_ok

def main():
    seed=int(sys.argv[sys.argv.index("--seed")+1]) if "--seed" in sys.argv else 23
    POP=int(sys.argv[sys.argv.index("--pop")+1]) if "--pop" in sys.argv else 14
    GENS=int(sys.argv[sys.argv.index("--gens")+1]) if "--gens" in sys.argv else 8
    random.seed(seed)
    cm_mod=_load(VENDOR/"core"/"credential_manager.py","cm")
    cm=cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True,auto_prompt=False): return 2
    log.info(f"auth {cm.credentials.username}  GAv4(gated-IV-pattern, non-IV) seed={seed} pop={POP} gens={GENS}")
    out=REPO/"WQ_GA_D0_GATED.json"; cache={}; hall=[]
    if out.exists():
        try:
            prev=json.load(open(out))
            for r in prev.get("hall",[]):
                if r.get("hash") and not r["hash"].startswith("bad"): cache[r["hash"]]=r; hall.append(r)
            hall.sort(key=lambda x:x["fit"],reverse=True)
            log.info(f"resumed {len(cache)} cached evaluations")
        except Exception as e: log.warning(f"resume failed: {e}")
    def evaluate(g,label=""):
        try: h=ghash(g); expr=render(g)
        except Exception as e:
            log.warning(f"   render-err: {str(e)[:60]}")
            return {"hash":"bad","label":label,"expr":"","settings":{},"genome":g,
                    "fit":-9.0,"submit_ok":False,"complexity":99,"ok":False,"sharpe":None,"turnover":None,"fitness":None,"self_corr":None,"alpha_id":None,"fails":[],"err":"render-err"}
        if h in cache: return cache[h]
        r=None
        for attempt in range(3):
            try:
                r=submit(cm.session,f"gag_{h}",expr,settings(g))
                if r.ok:
                    try: sc,_,_=fetch_self_corr(cm.session,r.alpha_id,timeout_s=90); r.self_corr=sc
                    except Exception as e: log.warning(f"   [{h}] sc net-err: {str(e)[:60]}"); r.self_corr=None
                break
            except Exception as e:
                log.warning(f"   [{h}] submit net-err (try {attempt+1}/3): {str(e)[:70]}")
                import time as _t; _t.sleep(20)
        if r is None:
            return {"hash":h,"label":label,"expr":expr,"settings":settings(g),"genome":g,
                    "fit":-9.0,"submit_ok":False,"complexity":complexity(g),"ok":False,"sharpe":None,"turnover":None,"fitness":None,"self_corr":None,"alpha_id":None,"fails":[],"err":"net-skip"}
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
        flag=" *** SUBMITTABLE ***" if ok else ""
        if r.ok: log.info(f"   [{h}]{(' '+label) if label else ''} fit={fit:+.3f} SH={r.sharpe:+.3f} TO={r.turnover:.3f} FIT={r.fitness:+.3f} sc={r.self_corr} fails={rec['fails']}{flag}")
        else: log.info(f"   [{h}]{(' '+label) if label else ''} FAILED: {str(r.error)[:80]}")
        return rec
    log.info("=== generation 1/%d (IV-pattern seeds with non-IV scores + random) ==="%GENS)
    pop=[]
    for name,g in SEEDS:
        rec=evaluate(g,label=name)
        if rec["submit_ok"]:
            log.info(f"!!! SUBMITTABLE non-IV gated [{rec['hash']}] {name} {rec['alpha_id']}")
            json.dump({"winner":rec,"hall":hall[:40]},open(out,"w"),indent=2)
            print(f"\n*** WINNER (seed {name}): {rec['alpha_id']} SH={rec['sharpe']} FIT={rec['fitness']} sc={rec['self_corr']}\n{rec['expr']}\n{rec['settings']}")
            return 0
        pop.append(g)
    pop+=[rand_genome() for _ in range(max(0,POP-len(pop)))]
    pop=pop[:max(POP,len(SEEDS))]
    for gen in range(2,GENS+1):
        scored=[(evaluate(g)["fit"], g) for g in pop]
        scored.sort(key=lambda x:x[0],reverse=True)
        b=cache.get(ghash(scored[0][1])) or {"sharpe":"?","self_corr":"?","complexity":"?","hash":"?","label":""}
        log.info(f"   gen{gen-1} best fit={scored[0][0]:+.3f} SH={b.get('sharpe')} sc={b.get('self_corr')} cx={b.get('complexity')} [{b.get('hash')}] {b.get('label','')}")
        log.info(f"=== generation {gen}/{GENS} ===")
        elite=[g for _,g in scored[:3]]; newpop=list(elite)
        def tourn():
            c=random.sample(scored,min(3,len(scored))); c.sort(key=lambda x:x[0],reverse=True); return c[0][1]
        while len(newpop)<POP:
            child=crossover(tourn(),tourn()) if random.random()<0.5 else json.loads(json.dumps(tourn()))
            child=mutate(child); newpop.append(child)
        pop=newpop
        for g in pop:
            rec=evaluate(g)
            if rec["submit_ok"]:
                log.info(f"!!! SUBMITTABLE non-IV gated gen{gen} [{rec['hash']}] {rec['alpha_id']}")
                json.dump({"winner":rec,"hall":sorted(hall,key=lambda x:x['fit'],reverse=True)[:40]},open(out,"w"),indent=2)
                print(f"\n*** WINNER: {rec['alpha_id']} SH={rec['sharpe']} FIT={rec['fitness']} sc={rec['self_corr']}\n{rec['expr']}\n{rec['settings']}")
                return 0
    hall.sort(key=lambda x:x["fit"],reverse=True)
    print("\n"+"="*110); print(f"GAv4 done, no submittable non-IV gated. Top ({len(cache)} evals):")
    for r in hall[:10]:
        print(f"  fit={r['fit']:+.3f} SH={r['sharpe']} TO={r['turnover']} FIT={r['fitness']} sc={r['self_corr']} fails={r['fails']} [{r['hash']}] {r.get('label','')}")
        print(f"      {r['expr'][:160].replace(chr(10),' | ')}")
    print("="*110)
    return 0
if __name__=="__main__": sys.exit(main() or 0)
