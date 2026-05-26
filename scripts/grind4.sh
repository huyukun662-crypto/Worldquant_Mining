#!/bin/bash
# Self-resuming grinder for batch-4: re-runs the miner until all candidates
# have an OK result (resume keeps OKs, retries errors/timeouts). Tolerates
# the container's intermittent clock-skew/TLS blips and clogged concurrent
# simulation slots.
cd /home/user/Worldquant_Mining
for attempt in 1 2 3 4 5 6 7 8; do
  echo "=== grind attempt $attempt (clock $(date -u +%H:%M:%S)) ==="
  python3 -m scripts.mine_uncommon --workers 2 --out UNCOMMON_MINING4.json --candidates candidates4.json 2>&1
  okc=$(python3 -c "import json;d=json.load(open('UNCOMMON_MINING4.json'));print(sum(1 for r in d if r.get('ok')))" 2>/dev/null || echo 0)
  echo "=== after attempt $attempt: ${okc}/10 ok ==="
  [ "$okc" -ge 10 ] && break
  sleep 45
done
echo "=== GRIND COMPLETE ==="
