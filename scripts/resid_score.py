"""Multivariate residual-Sharpe scorer (pure python). Regress candidate daily
PnL on the FULL pool jointly -> residual Sharpe (pool can't explain) + R^2.
The right predictor of WQ Performance Comparison; pairwise maxCorr misses
joint spanning."""
import json, sys, time, math
from pathlib import Path
import requests
from requests.auth import HTTPBasicAuth
API="https://api.worldquantbrain.com"; REPO=Path('/home/user/Worldquant_Mining')
def auth():
    u,p=json.load(open(REPO/'credential.txt')); s=requests.Session()
    s.auth=HTTPBasicAuth(u,p); s.post(f"{API}/authentication",timeout=20); return s
def get_pnl(s,aid,tries=8):
    for _ in range(tries):
        r=s.get(f"{API}/alphas/{aid}/recordsets/pnl",timeout=60)
        if r.status_code==200 and r.text.strip():
            return {d:v for d,v in r.json().get("records",[])}
        time.sleep(float(r.headers.get("Retry-After",2)))
    return {}
def daily(pnl):
    ds=sorted(pnl); cum=[pnl[d] for d in ds]
    return {ds[i]:cum[i]-cum[i-1] for i in range(1,len(ds))}
def solve(A,b):  # gaussian elim, n small
    n=len(A); M=[row[:]+[b[i]] for i,row in enumerate(A)]
    for c in range(n):
        p=max(range(c,n),key=lambda r:abs(M[r][c]))
        M[c],M[p]=M[p],M[c]
        if abs(M[c][c])<1e-12: continue
        for r in range(n):
            if r!=c:
                f=M[r][c]/M[c][c]
                M[r]=[M[r][k]-f*M[c][k] for k in range(n+1)]
    return [M[i][n]/M[i][i] if abs(M[i][i])>1e-12 else 0.0 for i in range(n)]
def corr(x,y):
    n=len(x); mx=sum(x)/n; my=sum(y)/n
    sxy=sum((a-mx)*(b-my) for a,b in zip(x,y))
    sxx=sum((a-mx)**2 for a in x); syy=sum((b-my)**2 for b in y)
    return sxy/math.sqrt(sxx*syy) if sxx>0 and syy>0 else 0.0
pool=json.load(open(REPO/'constants/delay0_pool_pnl.json'))
pd_,pr_=pool["dates"],pool["returns"]
pool_by={pid:{pd_[k+1]:pr[k] for k in range(len(pr))} for pid,pr in pr_.items()}
pids=list(pool_by); s=auth(); rows=json.load(open(sys.argv[1]))
print(f"pool = {len(pids)} alphas {pids}\n")
print(f"{'id':>9} {'SH':>5} {'maxC':>5} {'R2':>5} {'residSH':>7}  keep")
res=[]
for r in rows:
    if not r.get("ok"): continue
    aid=r["alpha_id"]; cret=daily(get_pnl(s,aid))
    dates=[d for d in cret if all(d in pool_by[p] for p in pids)]
    if len(dates)<100: continue
    y=[cret[d] for d in dates]
    cols=[[pool_by[p][d] for d in dates] for p in pids]
    k=len(cols)
    A=[[sum(cols[i][t]*cols[j][t] for t in range(len(dates))) for j in range(k)] for i in range(k)]
    bb=[sum(cols[i][t]*y[t] for t in range(len(dates))) for i in range(k)]
    beta=solve(A,bb)
    resid=[y[t]-sum(beta[i]*cols[i][t] for i in range(k)) for t in range(len(dates))]
    my=sum(y)/len(y); ss_tot=sum((v-my)**2 for v in y); ss_res=sum(v*v for v in resid)
    r2=1-ss_res/ss_tot if ss_tot>0 else 0
    mr=sum(resid)/len(resid); sd=math.sqrt(sum((v-mr)**2 for v in resid)/len(resid))
    resid_sh=mr/sd*math.sqrt(252) if sd>0 else 0
    maxc=max(abs(corr(y,[pool_by[p][d] for d in dates])) for p in pids)
    keep="ADD" if resid_sh>1.25 and r2<0.5 else "drop"
    res.append((resid_sh,aid,r["sharpe"],maxc,r2,keep))
for resid_sh,aid,sh,maxc,r2,keep in sorted(res,reverse=True):
    print(f"{aid:>9} {sh:5.2f} {maxc:5.2f} {r2:5.2f} {resid_sh:7.2f}  {keep}")
