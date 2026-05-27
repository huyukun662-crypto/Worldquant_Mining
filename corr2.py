import importlib.util, time, math
from pathlib import Path
REPO=Path('/home/user/Worldquant_Mining')
spec=importlib.util.spec_from_file_location('cm', REPO/'vendor/worldquant-miner/core/credential_manager.py')
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
cm=m.CredentialManager(base_path=str(REPO)); cm.authenticate(auto_load=True, auto_prompt=False)
s=cm.session
def get_pnl(a):
    for i in range(12):
        try: r=s.get(f"https://api.worldquantbrain.com/alphas/{a}/recordsets/pnl", timeout=40)
        except Exception: time.sleep(5); continue
        if r.status_code==200 and r.text.strip():
            try: return {x[0]:float(x[1]) for x in r.json().get("records",[]) if x[1] is not None}
            except Exception: time.sleep(4); continue
        time.sleep(5)
    return {}
def daily(d):
    k=sorted(d); return {k[i+1]:d[k[i+1]]-d[k[i]] for i in range(len(k)-1)}
def corr(x,y):
    n=len(x); mx=sum(x)/n; my=sum(y)/n
    sxy=sum((a-mx)*(b-my) for a,b in zip(x,y)); sxx=sum((a-mx)**2 for a in x); syy=sum((b-my)**2 for b in y)
    return sxy/math.sqrt(sxx*syy) if sxx>0 and syy>0 else float('nan')
P=daily(get_pnl("P0vp2jpx"))
print("correlation vs P0vp2jpx (submittable need <0.7):")
for aid,lbl in [("9qJ7V2GK","2.22/1.56 rev0.4"),("MPkLaPPo","2.18/1.55 rev0.7"),("d5dRO9EK","2.12/1.49 decayrev"),("QPE93rVg","2.00/1.48 noREV")]:
    A=daily(get_pnl(aid)); common=sorted(set(A)&set(P))
    c=corr([A[t] for t in common],[P[t] for t in common]) if len(common)>30 else float('nan')
    print(f"  {aid} ({lbl}): corr={c:.3f}  {'INDEPENDENT' if c<0.7 else 'TOO CORRELATED'}")
