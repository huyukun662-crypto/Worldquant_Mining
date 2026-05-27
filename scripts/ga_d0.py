"""Genetic algorithm to evolve submittable D0 (delay=0) NON-IV factors on WQ.

Genome = a fixed-shape "recipe": K weighted terms + global params.
  term  = sign * weight * group_op( ts_op( ratio(field_num[, field_den]), window ) )
  expr  = signed_power( sum(terms), amp )         (amp=1 -> no signed_power)
  globals = neutralization, decay, truncation, amp, K

Fitness (climb) = sharpe + 0.6*fitness - penalties(turnover, hard-FAILs).
STOP (submittable competition-grade) = no FAIL check (excl PENDING) AND
self_corr<0.7.  NO implied_volatility / option fields anywhere.
delay=0. WQ /simulations is the evaluator.
"""
from __future__ import annotations
import json, sys, random, hashlib, time
from pathlib import Path
from dataclasses import asdict
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mine_cold_fields import (submit, fetch_self_corr, _load, VENDOR, REPO, log)

# ---- gene pools (NO IV / option fields) ----
PV   = ["close","open","high","low","volume","vwap","returns","cap","adv20"]
FUND = ["assets","equity","ebit","ebitda","sales","cogs","capex","bookvalue_ps",
        "cashflow_op","debt","cash","assets_curr"]            # need ts_backfill
FIELDS = PV + FUND
TSOPS  = ["id","zscore","mean","delta","std","rank","sum","decay"]
GROUPS = ["gr_sub","gr_mkt","gr_ind","gr_sec","rank","zscore","scale"]
WINDOWS= [5,10,20,44,60,120,250]
WEIGHTS= [0.3,0.5,0.7,1.0]
SIGNS  = [-1.0,1.0]
NEUT   = ["MARKET","SUBINDUSTRY","INDUSTRY","SECTOR"]
DECAY  = [0,4,8,12]
TRUNC  = [0.02,0.05,0.08,0.10]
AMP    = [1,1,1,2,3]          # bias toward no-amp
KS     = [2,3,4]

def fld(f):
    return f"ts_backfill({f},250)" if f in FUND else f
def render_ratio(t):
    n=fld(t["num"])
    if t.get("den") and t["den"]!=t["num"]: return f"divide({n},{fld(t['den'])})"
    return n
def render_tsop(x,op,w):
    return {"id":x,"zscore":f"ts_zscore({x},{w})","mean":f"ts_mean({x},{w})",
            "delta":f"ts_delta({x},{w})","std":f"ts_std_dev({x},{w})",
            "rank":f"ts_rank({x},{w})","sum":f"ts_sum({x},{w})",
            "decay":f"ts_decay_linear({x},{w})"}[op]
def render_group(x,g):
    return {"gr_sub":f"group_rank({x},subindustry)","gr_mkt":f"group_rank({x},market)",
            "gr_ind":f"group_rank({x},industry)","gr_sec":f"group_rank({x},sector)",
            "rank":f"rank({x})","zscore":f"zscore({x})","scale":f"scale({x})"}[g]
def render_term(t):
    return render_group(render_tsop(render_ratio(t),t["op"],t["w"]),t["grp"])
def render(genome):
    expr="".join(f"{t['sign']*t['weight']:+g}*{render_term(t)}" for t in genome["terms"])
    if expr.startswith("+"): expr=expr[1:]
    if genome["amp"]>1: expr=f"signed_power({expr},{genome['amp']})"
    return expr
def settings(genome):
    return {"delay":0,"universe":"TOP3000","decay":genome["decay"],
            "truncation":genome["trunc"],"neutralization":genome["neut"]}

def rand_term():
    ratio = random.random()<0.35
    num=random.choice(FIELDS)
    den=random.choice(FUND) if ratio else None
    # ratios of pv price fields are also useful (e.g. close/vwap)
    if ratio and random.random()<0.4: num,den=random.choice(PV),random.choice(["vwap","close","open"])
    return {"num":num,"den":den,"op":random.choice(TSOPS),"w":random.choice(WINDOWS),
            "grp":random.choice(GROUPS),"sign":random.choice(SIGNS),"weight":random.choice(WEIGHTS)}
def rand_genome():
    k=random.choice(KS)
    return {"terms":[rand_term() for _ in range(k)],"neut":random.choice(NEUT),
            "decay":random.choice(DECAY),"trunc":random.choice(TRUNC),"amp":random.choice(AMP)}

def seed_genomes():
    # bias the search with the best-known D0 composite shape
    base={"neut":"MARKET","decay":12,"trunc":0.10,"amp":3,"terms":[
        {"num":"close","den":None,"op":"zscore","w":20,"grp":"gr_sub","sign":-1.0,"weight":1.0},
        {"num":"capex","den":"assets","op":"id","w":20,"grp":"gr_sub","sign":1.0,"weight":0.5},
        {"num":"bookvalue_ps","den":"close","op":"id","w":20,"grp":"gr_sub","sign":1.0,"weight":0.5},
        {"num":"sales","den":"assets","op":"id","w":20,"grp":"gr_sub","sign":1.0,"weight":0.5}]}
    return [base]

def mutate(g):
    g=json.loads(json.dumps(g))
    r=random.random()
    if r<0.5:  # mutate a term gene
        t=random.choice(g["terms"]); key=random.choice(["num","den","op","w","grp","sign","weight"])
        if key=="num": t["num"]=random.choice(FIELDS)
        elif key=="den": t["den"]=random.choice([None]+FUND)
        elif key=="op": t["op"]=random.choice(TSOPS)
        elif key=="w": t["w"]=random.choice(WINDOWS)
        elif key=="grp": t["grp"]=random.choice(GROUPS)
        elif key=="sign": t["sign"]*=-1
        else: t["weight"]=random.choice(WEIGHTS)
    elif r<0.7:  # global param
        k=random.choice(["neut","decay","trunc","amp"]); g[k]=random.choice({"neut":NEUT,"decay":DECAY,"trunc":TRUNC,"amp":AMP}[k])
    elif r<0.85 and len(g["terms"])<4:  # add term
        g["terms"].append(rand_term())
    elif len(g["terms"])>2:  # drop term
        g["terms"].pop(random.randrange(len(g["terms"])))
    return g
def crossover(a,b):
    c=json.loads(json.dumps(a))
    # mix terms
    pool=a["terms"]+b["terms"]; k=random.choice(KS)
    c["terms"]=random.sample(pool,min(k,len(pool)))
    for key in ["neut","decay","trunc","amp"]:
        c[key]=random.choice([a[key],b[key]])
    return c

def ghash(g): return hashlib.md5(render(g).encode()).hexdigest()[:10]

def fitness(r):
    if not r or not r.ok: return -9.0, False
    hard=[c for c in r.checks if c.get("result")=="FAIL"]
    # submittable = no FAIL (excluding pending) AND self-corr<0.7
    submit_ok = (len(hard)==0) and (r.self_corr is None or abs(r.self_corr)<0.7)
    f = r.sharpe + 0.6*r.fitness
    if r.turnover>0.30: f -= (r.turnover-0.30)*3.0
    # penalize non-sharpe/fitness FAILs (concentration etc.) harder
    for c in hard:
        if c.get("name") not in ("LOW_SHARPE","LOW_FITNESS"): f -= 0.5
    return f, submit_ok

def main():
    seed=int(sys.argv[sys.argv.index("--seed")+1]) if "--seed" in sys.argv else 7
    POP=int(sys.argv[sys.argv.index("--pop")+1]) if "--pop" in sys.argv else 12
    GENS=int(sys.argv[sys.argv.index("--gens")+1]) if "--gens" in sys.argv else 8
    random.seed(seed)
    cm_mod=_load(VENDOR/"core"/"credential_manager.py","cm")
    cm=cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True,auto_prompt=False): return 2
    log.info(f"auth {cm.credentials.username}  GA seed={seed} pop={POP} gens={GENS}")
    out=REPO/"WQ_GA_D0.json"; cache={}; hall=[]  # hall of fame
    def evaluate(g):
        h=ghash(g)
        if h in cache: return cache[h]
        expr=render(g)
        r=submit(cm.session, f"ga_{h}", expr, settings(g))
        if r.ok:
            sc,_,_=fetch_self_corr(cm.session, r.alpha_id, timeout_s=90); r.self_corr=sc
        fit,ok=fitness(r)
        rec={"hash":h,"expr":expr,"settings":settings(g),"genome":g,"fit":fit,"submit_ok":ok,
             "ok":r.ok,"sharpe":getattr(r,"sharpe",None),"turnover":getattr(r,"turnover",None),
             "fitness":getattr(r,"fitness",None),"self_corr":getattr(r,"self_corr",None),
             "alpha_id":getattr(r,"alpha_id",None),
             "fails":[c.get("name") for c in getattr(r,"checks",[]) if c.get("result")=="FAIL"],
             "err":getattr(r,"error",None)}
        cache[h]=rec; hall.append(rec)
        hall.sort(key=lambda x:x["fit"],reverse=True)
        json.dump({"hall":hall[:40],"n_eval":len(cache)},open(out,"w"),indent=2)
        flag=" *** SUBMITTABLE ***" if ok else ""
        if r.ok: log.info(f"   [{h}] fit={fit:+.3f} SH={r.sharpe:+.3f} TO={r.turnover:.3f} FIT={r.fitness:+.3f} sc={r.self_corr} fails={rec['fails']}{flag}")
        else: log.info(f"   [{h}] FAILED: {str(r.error)[:90]}")
        return rec
    # init population
    pop=seed_genomes(); pop+= [rand_genome() for _ in range(POP-len(pop))]
    best=None
    for gen in range(1,GENS+1):
        log.info(f"=== generation {gen}/{GENS} (pop {len(pop)}) ===")
        scored=[]
        for g in pop:
            rec=evaluate(g); scored.append((rec["fit"],g,rec))
            if rec["submit_ok"]:
                log.info(f"!!! SUBMITTABLE D0 FOUND gen{gen} [{rec['hash']}] {rec['alpha_id']} SH={rec['sharpe']} FIT={rec['fitness']}")
                best=rec
                json.dump({"hall":sorted(hall,key=lambda x:x['fit'],reverse=True)[:40],"winner":rec,"n_eval":len(cache)},open(out,"w"),indent=2)
                print(f"\n*** SUBMITTABLE D0: {rec['alpha_id']}  SH={rec['sharpe']} FIT={rec['fitness']} sc={rec['self_corr']}\n{rec['expr']}\n{rec['settings']}")
                return 0
        scored.sort(key=lambda x:x[0],reverse=True)
        log.info(f"   gen{gen} best fit={scored[0][0]:+.3f} SH={scored[0][2]['sharpe']} FIT={scored[0][2]['fitness']} [{scored[0][2]['hash']}]")
        # next gen: elitism + tournament selection + crossover + mutation
        elite=[g for _,g,_ in scored[:3]]
        newpop=list(elite)
        def tourn():
            cand=random.sample(scored,min(3,len(scored))); cand.sort(key=lambda x:x[0],reverse=True); return cand[0][1]
        while len(newpop)<POP:
            child=crossover(tourn(),tourn()) if random.random()<0.6 else json.loads(json.dumps(tourn()))
            child=mutate(child)
            if random.random()<0.4: child=mutate(child)
            newpop.append(child)
        pop=newpop
    # no submittable; report best
    hall.sort(key=lambda x:x["fit"],reverse=True)
    print("\n"+"="*110); print(f"GA done, no submittable D0. Top by fitness ({len(cache)} evals):")
    for r in hall[:12]:
        print(f"  fit={r['fit']:+.3f} SH={r['sharpe']} TO={r['turnover']} FIT={r['fitness']} sc={r['self_corr']} fails={r['fails']} [{r['hash']}]")
        print(f"      {r['expr'][:140]}")
    print("="*110)
    return 0
if __name__=="__main__": sys.exit(main() or 0)
