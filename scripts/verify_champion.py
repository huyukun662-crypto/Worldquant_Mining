"""Serial, rate-limit-gentle re-simulation + PRE-SUBMIT CHECK of D0 candidates.

For each (tag, expr, settings): simulate -> /check (enforce non-empty) ->
self-correlation. Saves full evidence to WQ_D0_SUBMISSION_CHECK.json so the
result persists even if the (unsubmitted) alpha is later garbage-collected.
"""
import sys, json, time
sys.path.insert(0, "/home/user/Worldquant_Mining/scripts")
import wq_lib
API = "https://api.worldquantbrain.com"

def fetch_checks(s, aid, tries=25, interval=10):
    for _ in range(tries):
        r = s.get(f"{API}/alphas/{aid}/check", timeout=30)
        if r.status_code == 200 and r.text.strip():
            checks = (r.json().get("is", {}) or {}).get("checks", []) or []
            if len(checks) >= 8:
                # require SELF_CORRELATION resolved too
                sc = next((c for c in checks if c["name"]=="SELF_CORRELATION"), None)
                if sc and sc.get("result") in ("PASS","FAIL"):
                    return checks
        time.sleep(interval)
    return checks if 'checks' in dir() else []

def self_corr_max(s, aid):
    r = s.get(f"{API}/alphas/{aid}/correlations/self", timeout=30)
    if r.status_code==200 and r.text.strip():
        jd=r.json(); recs=jd.get("records",[])
        mx=max((row[3] for row in recs if isinstance(row[3],(int,float))), default=None)
        top=[row for row in recs if len(row)>4 and row[4]]
        return mx, top[:5]
    return None, []

def run(cands, out="WQ_D0_SUBMISSION_CHECK.json"):
    s = wq_lib.auth()
    evidence=[]
    for tag, expr, settings in cands:
        print(f"\n{'='*90}\n[{tag}] simulating: {expr}\n  settings={settings}", flush=True)
        res = wq_lib.simulate(s, expr, settings)
        if not res.get("ok"):
            print(f"  SIM FAILED: {res.get('error')}", flush=True)
            evidence.append({"tag":tag,"expr":expr,"settings":settings,"sim_ok":False,"error":res.get("error")})
            json.dump(evidence, open(out,"w"), indent=2); continue
        aid=res["alpha_id"]
        print(f"  alpha_id={aid}  SH={res['sharpe']} TO={res['turnover']} FIT={res['fitness']} "
              f"RET={res['returns']} DD={res['drawdown']} L/S={res['longCount']}/{res['shortCount']}", flush=True)
        time.sleep(3)
        checks = fetch_checks(s, aid)
        mx, top = self_corr_max(s, aid)
        nonpass=[c for c in checks if c.get('result')!='PASS']
        verdict = len(checks)>=8 and len(nonpass)==0
        print(f"  --- {len(checks)} submission checks ---", flush=True)
        for c in checks:
            print(f"    {c.get('result'):<8}{c.get('name'):<24} limit={c.get('limit')} value={c.get('value')}", flush=True)
        print(f"  self-corr precise max={mx}  most-correlated={top}", flush=True)
        print(f"  >>> {tag} SUBMITTABLE = {verdict}", flush=True)
        evidence.append({"tag":tag,"expr":expr,"settings":{**wq_lib.D0_DEFAULT,**settings},
                         "sim_ok":True,"alpha_id":aid,
                         "sharpe":res["sharpe"],"turnover":res["turnover"],"fitness":res["fitness"],
                         "returns":res["returns"],"drawdown":res["drawdown"],
                         "longCount":res["longCount"],"shortCount":res["shortCount"],
                         "checks":checks,"self_corr_max":mx,"submittable":verdict})
        json.dump(evidence, open(out,"w"), indent=2)
        time.sleep(5)
    print(f"\nwrote {out}")
    return evidence

if __name__ == "__main__":
    # SUBMITTABLE D0 IV factor (user allowed IV): 20-day put-call implied-vol
    # skew. Different tenor from the account's 60/180-day skew alphas, so
    # SELF_CORRELATION PASSes. Reproduced + persisted: Sharpe ~2.10, Fitness
    # ~1.49, self-corr ~0.687 (borderline), all /check PASS -> SUBMITTABLE.
    CHAMPION = ("zscore(ts_backfill(subtract("
        "implied_volatility_call_20,implied_volatility_put_20),5))")
    CANDS = [
        ("D0_IV_SKEW20", CHAMPION,
         {"universe":"TOP3000","delay":0,"decay":8,"truncation":0.05,"neutralization":"SUBINDUSTRY"}),
    ]
    run(CANDS)
