#!/usr/bin/env python3
"""Genetic algorithm to mine D0 (delay=0) NON-IV factors that pass the IQC2026S2
competition gates (SH>=2.0, FIT>=1.3, 0.01<TO<0.7, CONCENTRATED_WEIGHT) AND are
independent (daily-PnL corr < 0.7) of the already-submitted factor 9qJ7V2GK.

Genome = sparse weight vector over a pool of D0 non-IV base signals (group-zscored,
subindustry).  Fitness rewards approaching the gates and hard-penalizes corr>=0.7.
Evaluation = WQ /simulations (reuses mine_d0.submit_one), then /recordsets/pnl for corr.
"""
import importlib.util, time, json, random, math, sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

REPO = Path('/home/user/Worldquant_Mining')
# import mine_d0 machinery
spec = importlib.util.spec_from_file_location('mine_d0', REPO/'scripts'/'mine_d0.py')
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
cm = M.cm if hasattr(M, 'cm') else None
# mine_d0 authenticates at import via its own cm; grab the session
session = None
for attr in dir(M):
    pass
# mine_d0 builds cm in main(); instead authenticate fresh here
spec2 = importlib.util.spec_from_file_location('cmmod', REPO/'vendor/worldquant-miner/core/credential_manager.py')
cmm = importlib.util.module_from_spec(spec2); spec2.loader.exec_module(cmm)
CM = cmm.CredentialManager(base_path=str(REPO)); CM.authenticate(auto_load=True, auto_prompt=False)
S = CM.session

REF_ALPHA = "9qJ7V2GK"   # submitted; new factor must be corr<0.7 with this

# ---- base signal pool (D0 non-IV).  Each is a unitless group_zscore at subindustry. ----
SI   = "group_zscore(ts_mean(ts_backfill(news_short_interest, 22), 22), subindustry)"
DR90 = "group_zscore(ts_mean(ts_backfill(news_pct_90min, 5), 10), subindustry)"
DR120= "group_zscore(ts_mean(ts_backfill(news_pct_120min, 5), 10), subindustry)"
PERAT= "group_zscore(ts_mean(ts_backfill(news_pe_ratio, 22), 22), subindustry)"
REV5 = "group_zscore(ts_delta(close, 5), subindustry)"
REV1 = "group_zscore(ts_delta(close, 1), subindustry)"
MAREV= "group_zscore(divide(close, ts_mean(close, 10)), subindustry)"
VOL  = "group_zscore(ts_std_dev(returns, 20), subindustry)"
MOM  = "group_zscore(divide(close, ts_backfill(close, 250)), subindustry)"
VOLU = "group_zscore(ts_delta(volume, 5), subindustry)"
VWAPR= "group_zscore(divide(close, vwap), subindustry)"
EY   = "group_zscore(ts_backfill(divide(est_epsr, close), 120), subindustry)"
BY   = "group_zscore(ts_backfill(divide(est_bookvalue_ps, close), 120), subindustry)"
ROA  = "group_zscore(ts_backfill(divide(est_netprofit, est_tot_assets), 120), subindustry)"
ROE  = "group_zscore(ts_backfill(divide(est_netprofit, est_shequity), 120), subindustry)"
EBITA= "group_zscore(ts_backfill(divide(est_ebit, est_tot_assets), 120), subindustry)"
REVS = "group_zscore(ts_delta(ts_backfill(est_epsr, 120), 66), subindustry)"
RPQ  = "group_zscore(ts_mean(ts_backfill(vec_avg(nws18_qcm), 22), 22), subindustry)"
RPG  = "group_zscore(ts_mean(ts_backfill(vec_avg(nws18_ghc_lna), 22), 22), subindustry)"
PEER = "group_zscore(rel_ret_all, subindustry)"
PEERC= "group_zscore(rel_ret_comp, subindustry)"
SOCS = "group_zscore(ts_mean(ts_backfill(scl12_sentiment, 22), 22), subindustry)"
SOCB = "group_zscore(ts_mean(ts_backfill(snt_buzz, 22), 22), subindustry)"

POOL = [("SI",SI),("DR90",DR90),("DR120",DR120),("PERAT",PERAT),("REV5",REV5),
        ("REV1",REV1),("MAREV",MAREV),("VOL",VOL),("MOM",MOM),("VOLU",VOLU),
        ("VWAPR",VWAPR),("EY",EY),("BY",BY),("ROA",ROA),("ROE",ROE),("EBITA",EBITA),
        ("REVS",REVS),("RPQ",RPQ),("RPG",RPG),("PEER",PEER),("PEERC",PEERC),
        ("SOCS",SOCS),("SOCB",SOCB)]
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
    sxy=sum((p-mx)*(q-my) for p,q in zip(x,y)); sxx=sum((p-mx)**2 for p in x); syy=sum((q-my)**2 for q in y)
    return sxy/math.sqrt(sxx*syy) if sxx>0 and syy>0 else 1.0

REFD = daily(get_pnl(REF_ALPHA))
print(f"[ref] 9qJ7V2GK pnl pts={len(REFD)}", flush=True)

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
    # correlation vs submitted ref
    c=corr(daily(get_pnl(aid)), REFD)
    # fitness: reward gate margins, hard penalty for corr>=0.7 and conc fail
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
    k=random.randint(2,5); idx=random.sample(range(NPOOL),k)
    return {i:random.choice(WEIGHTS) for i in idx}

def mutate(g):
    g=dict(g)
    op=random.random()
    if op<0.4 and g:  # perturb a weight
        i=random.choice(list(g)); g[i]=random.choice(WEIGHTS)
    elif op<0.7:      # add a signal
        i=random.randrange(NPOOL); g[i]=random.choice(WEIGHTS)
    elif op<0.85 and len(g)>2:  # drop
        del g[random.choice(list(g))]
    else:             # nudge weight
        if g:
            i=random.choice(list(g)); g[i]=round(max(-2,min(2,g[i]+random.choice([-0.5,0.5]))),1) or 0.5
    return {i:w for i,w in g.items() if w}

def crossover(a,b):
    keys=set(a)|set(b); child={}
    for k in keys:
        src=a if (k in a and (k not in b or random.random()<0.5)) else b
        if k in src and src[k]: child[k]=src[k]
    if len(child)<2: child=rand_genome()
    return child

def G(**kw):  # build genome from signal names
    return {NAME2IDX[k]:v for k,v in kw.items()}

# seed population with known-good non-SI optimum + light-SI boundary variants + orthogonal-heavy
SEEDS = [
    G(REV5=-1.3, DR90=1.8, DR120=1, EY=1, RPQ=-1.3),               # 1.95 non-SI optimum
    G(REV5=-1.5, DR90=1.5, EY=1.3, RPQ=-1.3, VOL=-0.5),            # +vol orthogonal
    G(SI=0.3, REV5=-1.3, DR90=1.8, DR120=1, EY=1, RPQ=-1.3),       # light-SI (corr headroom test)
    G(SI=0.5, REV5=-1.3, DR90=1.5, EY=1, RPQ=-1.3, ROA=0.7, PEER=-0.5),  # SI + extra orthogonal
    G(REV5=-1.3, DR90=1.5, DR120=1, EY=1, RPQ=-1, RPG=-0.7, ROA=0.5),    # orthogonal-heavy
    G(SI=0.3, REV5=-1, DR90=1.5, EY=1, RPQ=-1, ROA=0.7, EBITA=-0.5, PEER=-0.5),
]
POP=10; GENS=8; ELITE=3
random.seed(42)
pop=SEEDS + [rand_genome() for _ in range(POP-len(SEEDS))]
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
            print(f"  gen{gen} fit={fitv:.2f} SH={r.get('sharpe')} FIT={r.get('fitness')} TO={r.get('turnover')} corr={r.get('corr')} cw={r.get('conc')} {r.get('alpha_id')} {tag}", flush=True)
    top=scored[0]
    if best is None or top[0]>best[0]: best=top
    hist.append({"gen":gen,"best_fit":top[0],"best":top[2]})
    json.dump({"hist":hist,"best":best[2]}, open(REPO/'D0_GA.json','w'), indent=2)
    print(f"[gen{gen}] best fit={top[0]:.2f} {top[2].get('alpha_id')} passed={top[2].get('passed')}", flush=True)
    # next generation
    elites=[g for _,g,_ in scored[:ELITE]]
    newpop=list(elites)
    while len(newpop)<POP:
        a=random.choice(scored[:5])[1]; b=random.choice(scored[:5])[1]
        child=mutate(crossover(a,b))
        newpop.append(child)
    pop=newpop
print("[done] best:", json.dumps(best[2]), flush=True)
