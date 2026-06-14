#!/bin/bash
# Guarded auto-miner: only spends simulation quota when the platform is fast.
# 1. Probe latency with ONE regression sim.
# 2. If it returns quickly (< THRESH s), the platform is in a good window ->
#    launch the decorrelated-IV regression batch (resume-aware).
# 3. Report any PASS-ALL factor with SH > 1.5 (the robust low-corr sibling target).
# Designed to be invoked repeatedly (e.g. via /loop) -- it is cheap & idempotent
# during congestion (just the probe), and only mines when sims complete fast.
cd /home/user/Worldquant_Mining
THRESH=200
probe=$(timeout 230 python3 - <<'PY' 2>/dev/null | tail -1
import scripts.mine_uncommon as M, time
cm=M._load(M.VENDOR/'core'/'credential_manager.py','cm').CredentialManager(base_path=str(M.REPO))
cm.authenticate(auto_load=True,auto_prompt=False)
s={'universe':'TOP3000','delay':1,'decay':4,'neutralization':'SUBINDUSTRY','truncation':0.08}
expr='reverse(zscore(ts_decay_linear(ts_regression(returns, ts_backfill(implied_volatility_mean_60,5), 60),15)))'
t=time.time(); r=M.submit_and_poll(cm.session, expr, s, timeout=210)
print('PROBE', int(time.time()-t) if r.get('ok') else 999)
PY
)
lat=$(echo "$probe" | grep -oE '[0-9]+$' || echo 999)
echo "PROBE latency=${lat}s threshold=${THRESH}s clock=$(date -u +%H:%M:%S)"
if [ "$lat" -ge "$THRESH" ]; then
  echo "CONGESTED -- skipping mining this round (no quota spent on batch)"
  exit 0
fi
echo "FAST WINDOW -- launching decorrelated-IV regression batch"
python3 -m scripts.mine_uncommon --workers 3 --poll-timeout 400 \
    --out UNCOMMON_MINING16.json --candidates candidates16.json 2>&1 | tail -3
python3 - <<'PY'
import json,os
f='UNCOMMON_MINING16.json'
if not os.path.exists(f): print('no results'); raise SystemExit
d=json.load(open(f)); strong=[]
for r in d:
    if not r.get('ok'): continue
    c=r.get('checks',{}); allp=all(c.get(k)=='PASS' for k in ['LOW_SHARPE','LOW_FITNESS','LOW_TURNOVER','HIGH_TURNOVER','CONCENTRATED_WEIGHT','LOW_SUB_UNIVERSE_SHARPE'])
    if allp and (r.get('sharpe') or 0)>1.5: strong.append(r)
    print(f"  SH={r.get('sharpe'):+.2f} sub={c.get('LOW_SUB_UNIVERSE_SHARPE')} all={'PASS' if allp else 'no'} [{r.get('alpha_id')}]")
if strong:
    json.dump(strong, open('SIBLING_FOUND.json','w'), indent=2)
    print(f"*** FOUND {len(strong)} STRONG PASS-ALL SIBLING(S) -> SIBLING_FOUND.json ***")
else:
    print("no SH>1.5 PASS-ALL sibling yet")
PY
