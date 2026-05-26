#!/bin/bash
# Mine the ROBUST low-correlation sibling factors (non-IV families) once the
# environment is healthy again. These use ts_regression to pass sub-universe
# and are a DIFFERENT data family from the already-submitted option-IV factor
# Wj9gK1Jd, so self-correlation stays low.
#
# WHY THIS IS DEFERRED (2026-05-26): on the congested platform, ts_regression
# composites on non-IV (analyst/sentiment/news) fields exceed ~450-600s per
# simulation, and this container kills processes after ~10-15 min -- so a
# single such sim cannot finish. When sims complete in ~60-120s again (test
# with a trivial expr), run this; it self-resumes and keeps only OK results.
#
# Quick health check before running:
#   python3 - <<'PY'
#   import scripts.mine_uncommon as M,time
#   cm=M._load(M.VENDOR/'core'/'credential_manager.py','cm').CredentialManager(base_path=str(M.REPO))
#   cm.authenticate(auto_load=True,auto_prompt=False)
#   t=time.time(); r=M.submit_and_poll(cm.session,'rank(close)',{'universe':'TOP3000','delay':1,'decay':4,'neutralization':'SUBINDUSTRY','truncation':0.08},timeout=200)
#   print('latency',int(time.time()-t),'s ok',r.get('ok'))  # want < ~120s
#   PY
#
# Then:  setsid nohup bash scripts/mine_robust.sh > mine_robust.log 2>&1 &
cd /home/user/Worldquant_Mining
for cand in candidates12.json candidates4.json; do
  out="ROBUST_${cand%.json}.json"
  for attempt in $(seq 1 8); do
    echo "=== $cand attempt $attempt (clock $(date -u +%H:%M:%S)) ==="
    python3 -m scripts.mine_uncommon --workers 2 --poll-timeout 900 \
        --out "$out" --candidates "$cand" 2>&1
    okc=$(python3 -c "import json;d=json.load(open('$out'));print(sum(1 for r in d if r.get('ok')))" 2>/dev/null || echo 0)
    echo "=== $cand after attempt $attempt: ${okc} ok ==="
    [ "$okc" -ge 1 ] && break
    sleep 30
  done
done
echo "=== ROBUST MINING DONE -- check ROBUST_*.json for PASS-ALL + run self-corr vs Wj9gK1Jd ==="
