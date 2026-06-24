import importlib.util, sys, json, time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
REPO=Path('.').resolve()
spec=importlib.util.spec_from_file_location('mine_d1','scripts/mine_d1.py')
m=importlib.util.module_from_spec(spec); sys.modules['mine_d1']=m; spec.loader.exec_module(m)
cmmod=importlib.util.spec_from_file_location('cm', REPO/'vendor/worldquant-miner/core/credential_manager.py')
cmm=importlib.util.module_from_spec(cmmod); cmmod.loader.exec_module(cmm)
cm=cmm.CredentialManager(base_path=str(REPO)); cm.authenticate(auto_load=True,auto_prompt=False)
print("auth",cm.credentials.username,flush=True)

base='rank(winsorize(add(rank(-ts_corr(close, volume, 20)), rank(divide(-ts_delta(close, 10), ts_std_dev(returns, 10)))), std=4))'
longer='rank(winsorize(add(rank(-ts_corr(close, volume, 40)), rank(divide(-ts_delta(close, 20), ts_std_dev(returns, 20)))), std=4))'
jobs=[]
for expr,tag in [(base,'base'),(longer,'longer')]:
    for decay in [8,16,32]:
        jobs.append((tag,expr,decay))

def run(j):
    tag,expr,decay=j
    s={'universe':'TOP3000','neutralization':'SUBINDUSTRY','truncation':0.08,'decay':decay}
    r=m.submit(cm.session,expr,s)
    line=f"{tag} decay={decay} :: ok={r.ok} SH={r.sharpe:+.3f} TO={r.turnover:.3f} FIT={r.fitness:+.3f} DD={r.drawdown:.3f} checks={r.checks_passed}/{r.checks_total} submittable={r.submittable} fail={r.failed_checks} id={r.alpha_id} err={r.error[:60]}"
    print(line,flush=True)
    return r

results=[]
with ThreadPoolExecutor(max_workers=2) as ex:
    for r in ex.map(run, jobs):
        results.append({'expr':r.expression,'settings':r.settings,'sharpe':r.sharpe,'turnover':r.turnover,'fitness':r.fitness,'drawdown':r.drawdown,'submittable':r.submittable,'failed':r.failed_checks,'alpha_id':r.alpha_id,'ok':r.ok})
json.dump(results,open('WQ_D1_DECAY_SWEEP.json','w'),indent=2)
print("DONE",flush=True)
