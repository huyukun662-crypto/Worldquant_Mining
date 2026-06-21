import importlib.util, sys, json
from pathlib import Path
REPO=Path('.').resolve()
spec=importlib.util.spec_from_file_location('mine_d1','scripts/mine_d1.py')
m=importlib.util.module_from_spec(spec); sys.modules['mine_d1']=m; spec.loader.exec_module(m)
cmmod=importlib.util.spec_from_file_location('cm', REPO/'vendor/worldquant-miner/core/credential_manager.py')
cmm=importlib.util.module_from_spec(cmmod); cmmod.loader.exec_module(cmm)
cm=cmm.CredentialManager(base_path=str(REPO)); cm.authenticate(auto_load=True,auto_prompt=False)
print("auth ok",flush=True)
k4=open('/tmp/v4_k4.txt').read().strip()
k5=open('/tmp/v4_k5.txt').read().strip()
jobs=[('K4',k4,'SUBINDUSTRY',24),('K4',k4,'SUBINDUSTRY',48),
      ('K5',k5,'SUBINDUSTRY',32),('K4',k4,'INDUSTRY',16)]
out=[]
for tag,expr,neut,decay in jobs:
    s={'universe':'TOP3000','neutralization':neut,'truncation':0.08,'decay':decay}
    r=m.submit(cm.session,expr,s)
    print(f"{tag} {neut} decay={decay} :: SH={r.sharpe:+.3f} TO={r.turnover:.3f} FIT={r.fitness:+.3f} DD={r.drawdown:.3f} sub={r.submittable} fail={r.failed_checks} id={r.alpha_id} err={r.error[:40]}",flush=True)
    out.append({'tag':tag,'neut':neut,'decay':decay,'sharpe':r.sharpe,'turnover':r.turnover,'fitness':r.fitness,'drawdown':r.drawdown,'submittable':r.submittable,'alpha_id':r.alpha_id,'expression':expr,'ok':r.ok})
json.dump(out,open('WQ_D1_V4_TUNE.json','w'),indent=2)
print("DONE",flush=True)
