#!/usr/bin/env python3
"""Third D0 factor: GA targeting independence from 88nl8wAV.

Key differences from mine_ga.py:
- REF_ALPHA = "88nl8wAV" (second submitted factor)
- All signals wrapped with winsorize(std=4) for regularization
- Dense signals preferred (PEER, MOM, VOL, REV) → CONC_WEIGHT passes naturally
- Economic seeds: peer mean-reversion, earnings revision, low-volatility
- Simpler genomes: 2-4 terms only
- DR90/DR120 in pool so GA can optionally use news drift if needed
"""
import importlib.util, time, json, random, math, sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

REPO = Path('/home/user/Worldquant_Mining')
spec = importlib.util.spec_from_file_location('mine_d0', REPO/'scripts'/'mine_d0.py')
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
spec2 = importlib.util.spec_from_file_location('cmmod', REPO/'vendor/worldquant-miner/core/credential_manager.py')
cmm = importlib.util.module_from_spec(spec2); spec2.loader.exec_module(cmm)
CM = cmm.CredentialManager(base_path=str(REPO)); CM.authenticate(auto_load=True, auto_prompt=False)
S = CM.session

REF_ALPHA = "88nl8wAV"   # second submitted; new factor must have corr<0.7 with it

def wsor(sig): return f"winsorize({sig}, std=4)"

# Dense price/volume signals (all stocks have prices → no CONC_WEIGHT issue)
PEER  = wsor("group_zscore(rel_ret_all, subindustry)")
PEERC = wsor("group_zscore(rel_ret_comp, subindustry)")
MOM   = wsor("group_zscore(divide(close, ts_backfill(close, 250)), subindustry)")
VOL   = wsor("group_zscore(ts_std_dev(returns, 20), subindustry)")
REV5  = wsor("group_zscore(ts_delta(close, 5), subindustry)")
REV1  = wsor("group_zscore(ts_delta(close, 1), subindustry)")
MAREV = wsor("group_zscore(divide(close, ts_mean(close, 10)), subindustry)")
VOLU  = wsor("group_zscore(ts_delta(volume, 5), subindustry)")
VWAPR = wsor("group_zscore(divide(close, vwap), subindustry)")
# Fundamental / analyst (dense via ts_backfill)
EY    = wsor("group_zscore(ts_backfill(divide(est_epsr, close), 120), subindustry)")
BY    = wsor("group_zscore(ts_backfill(divide(est_bookvalue_ps, close), 120), subindustry)")
REVS  = wsor("group_zscore(ts_delta(ts_backfill(est_epsr, 120), 66), subindustry)")
ROA   = wsor("group_zscore(ts_backfill(divide(est_netprofit, est_tot_assets), 120), subindustry)")
# Social media (dense via backfill + mean smoothing)
SOCB  = wsor("group_zscore(ts_mean(ts_backfill(snt_buzz, 22), 22), subindustry)")
SOCS  = wsor("group_zscore(ts_mean(ts_backfill(scl12_sentiment, 22), 22), subindustry)")
# News drift (optional; GA will self-regulate via corr penalty vs 88nl8wAV)
DR90  = wsor("group_zscore(ts_mean(ts_backfill(news_pct_90min, 5), 10), subindustry)")
DR120 = wsor("group_zscore(ts_mean(ts_backfill(news_pct_120min, 5), 10), subindustry)")

POOL = [
    ("PEER",  PEER),    # Peer relative return (mean-reversion)
    ("PEERC", PEERC),   # Competitor return (mean-reversion)
    ("MOM",   MOM),     # 250-day price momentum
    ("VOL",   VOL),     # Realized volatility (low-vol)
    ("REV5",  REV5),    # 5-day price reversal
    ("REV1",  REV1),    # 1-day price reversal
    ("MAREV", MAREV),   # Moving-average reversal
    ("VOLU",  VOLU),    # Volume momentum
    ("VWAPR", VWAPR),   # VWAP premium (intraday)
    ("EY",    EY),      # Earnings yield (value)
    ("BY",    BY),      # Book yield (value)
    ("REVS",  REVS),    # Analyst revision momentum (quality/growth)
    ("ROA",   ROA),     # Return on assets (quality)
    ("SOCB",  SOCB),    # Social buzz (attention)
    ("SOCS",  SOCS),    # Social sentiment
    ("DR90",  DR90),    # 90-min news drift
    ("DR120", DR120),   # 120-min news drift
]
NPOOL = len(POOL)
NAME2IDX = {n:i for i,(n,_) in enumerate(POOL)}
WEIGHTS = [-2,-1.5,-1.3,-1,-0.7,-0.5,-0.3,0.3,0.5,0.7,1,1.3,1.5,1.8,2]

SETTINGS = {"instrumentType":"EQUITY","region":"USA","universe":"TOP3000","delay":0,
            "decay":4,"neutralization":"SUBINDUSTRY","truncation":0.05,
            "pasteurization":"ON","unitHandling":"VERIFY","nanHandling":"OFF",
            "language":"FASTEXPR","visualization":False}

def render(genome):
    terms=[f"multiply({POOL[i][1]}, {w})" for i,w in genome.items() if w]
    if not terms: return None
    e=terms[0]
    for t in terms[1:]: e=f"add({e}, {t})"
    return e

def get_pnl(aid):
    for i in range(8):
        try: r=S.get(f"https://api.worldquantbrain.com/alphas/{aid}/recordsets/pnl",timeout=40)
        except Exception: time.sleep(4); continue
        if r.status_code==200 and r.text.strip():
            try: return {x[0]:float(x[1]) for x in r.json().get("records",[]) if x[1] is not None}
            except Exception: time.sleep(3); continue
        time.sleep(4)
    return {}

def daily(d):
    k=sorted(d); return {k[i+1]:d[k[i+1]]-d[k[i]] for i in range(len(k)-1)}

def corr(a,b):
    c=sorted(set(a)&set(b))
    if len(c)<50: return 1.0
    x=[a[t] for t in c]; y=[b[t] for t in c]; n=len(x)
    mx=sum(x)/n; my=sum(y)/n
    sxy=sum((p-mx)*(q-my) for p,q in zip(x,y))
    sxx=sum((p-mx)**2 for p in x); syy=sum((q-my)**2 for q in y)
    return sxy/math.sqrt(sxx*syy) if sxx>0 and syy>0 else 1.0

REFD = daily(get_pnl(REF_ALPHA))
print(f"[ref] {REF_ALPHA} pnl pts={len(REFD)}", flush=True)

def evaluate(genome):
    expr=render(genome)
    if expr is None: return {"fit":-99,"expr":None}
    try:
        res=M.submit_one(S, expr, dict(SETTINGS))
    except Exception as e:
        return {"fit":-40,"expr":expr,"err":f"net:{type(e).__name__}"}
    if not res.get("ok") or res.get("sharpe") is None:
        return {"fit":-50,"expr":expr,"err":res.get("message") or res.get("stage")}
    sh=res["sharpe"]; ft=res["fitness"]; to=res["turnover"]; cw=res.get("conc_wt_pass")
    aid=res["alpha_id"]
    c=corr(daily(get_pnl(aid)), REFD)
    g_sh=min(sh/2.0, 1.15); g_ft=min(ft/1.3, 1.15)
    fit=g_sh + g_ft
    if cw: fit+=0.3
    else: fit-=0.5
    if to>=0.7 or to<=0.01: fit-=1.0
    if c>=0.7: fit-=3.0*(c-0.7+0.1)
    passed = sh>=2.0 and ft>=1.3 and cw and 0.01<to<0.7 and c<0.7
    if passed: fit+=5.0
    return {"fit":fit,"expr":expr,"sharpe":sh,"fitness":ft,"turnover":to,
            "conc":cw,"corr":round(c,3),"alpha_id":aid,"passed":passed}

def rand_genome():
    k=random.randint(2,4)
    idx=random.sample(range(NPOOL),k)
    return {i:random.choice(WEIGHTS) for i in idx}

def mutate(g):
    g=dict(g)
    op=random.random()
    if op<0.4 and g:
        i=random.choice(list(g)); g[i]=random.choice(WEIGHTS)
    elif op<0.7:
        i=random.randrange(NPOOL); g[i]=random.choice(WEIGHTS)
    elif op<0.85 and len(g)>2:
        del g[random.choice(list(g))]
    else:
        if g:
            i=random.choice(list(g))
            g[i]=round(max(-2,min(2,g[i]+random.choice([-0.5,0.5]))),1) or 0.5
    return {i:w for i,w in g.items() if w}

def crossover(a,b):
    keys=set(a)|set(b); child={}
    for k in keys:
        src=a if (k in a and (k not in b or random.random()<0.5)) else b
        if k in src and src[k]: child[k]=src[k]
    if len(child)<2: child=rand_genome()
    return child

def G(**kw): return {NAME2IDX[k]:v for k,v in kw.items()}

# Economic seeds - simple 2-4 term composites with clear meaning
SEEDS = [
    # Peer mean-reversion + earnings revision + value: buy laggards with improving fundamentals
    G(PEER=-1.5, REVS=1.0, EY=0.7),
    # Peer + short-term price reversal + analyst revision
    G(PEER=-1.3, REV5=-0.7, REVS=1.3),
    # Low-vol + earnings yield + book yield: quality-value factor
    G(VOL=-1.5, EY=1.0, BY=0.7),
    # Earnings revision momentum + value + reversal hedge
    G(REVS=1.8, EY=0.7, REV5=-0.7),
    # Social buzz + momentum + low-vol: attention-driven momentum
    G(SOCB=1.3, MOM=0.7, VOL=-0.7),
    # Competitor return mean-reversion + revision
    G(PEERC=-1.3, REVS=1.0, EY=0.5),
    # MA reversal + analyst revision + value
    G(MAREV=-1.5, REVS=1.0, EY=0.5),
    # News drift (anchor) + quality + reversal: keep DR90 but pair with non-news
    G(DR90=1.5, ROA=0.7, PEER=-0.7, REV5=-0.5),
]

POP=10; GENS=6; ELITE=3
random.seed(7)
pop=SEEDS + [rand_genome() for _ in range(max(0, POP-len(SEEDS)))]
hist=[]; best=None
for gen in range(GENS):
    with ThreadPoolExecutor(max_workers=M.MAX_CONCURRENT) as ex:
        futs={ex.submit(evaluate,g):g for g in pop}
        scored=[]
        for f in as_completed(futs):
            r=f.result(); g=futs[f]; scored.append((r["fit"],g,r))
    scored.sort(key=lambda x:-x[0])
    for fitv,g,r in scored:
        if r.get("alpha_id"):
            tag="*** PASS ***" if r.get("passed") else ""
            print(f"  gen{gen} fit={fitv:.2f} SH={r.get('sharpe')} FIT={r.get('fitness')} "
                  f"TO={r.get('turnover')} corr={r.get('corr')} cw={r.get('conc')} "
                  f"{r.get('alpha_id')} {tag}", flush=True)
    top=scored[0]
    if best is None or top[0]>best[0]: best=top
    hist.append({"gen":gen,"best_fit":top[0],"best":top[2]})
    json.dump({"hist":hist,"best":best[2]}, open(REPO/'D0_GA3.json','w'), indent=2)
    print(f"[gen{gen}] best fit={top[0]:.2f} {top[2].get('alpha_id')} passed={top[2].get('passed')}", flush=True)
    elites=[g for _,g,_ in scored[:ELITE]]
    newpop=list(elites)
    while len(newpop)<POP:
        a=random.choice(scored[:5])[1]; b=random.choice(scored[:5])[1]
        child=mutate(crossover(a,b))
        newpop.append(child)
    pop=newpop
print("[done] best:", json.dumps(best[2]), flush=True)
