#!/bin/bash
# Self-resuming grinder for the STRONG composite candidates (batch-4).
# These use ts_regression and are heavy: on the congested platform they can
# take 600-1000s each, so poll-timeout is high and we re-run until all land.
# Tolerates the container's intermittent clock-skew/TLS blips (miner retries
# auth) and clogged concurrent-sim slots (patient 429 backoff + Location fix).
cd /home/user/Worldquant_Mining
for attempt in $(seq 1 12); do
  echo "=== grind attempt $attempt (clock $(date -u +%H:%M:%S)) ==="
  python3 -m scripts.mine_uncommon --workers 2 --poll-timeout 1000 \
      --out UNCOMMON_MINING4.json --candidates candidates4.json 2>&1
  okc=$(python3 -c "import json;d=json.load(open('UNCOMMON_MINING4.json'));print(sum(1 for r in d if r.get('ok')))" 2>/dev/null || echo 0)
  echo "=== after attempt $attempt: ${okc}/10 ok ==="
  [ "$okc" -ge 10 ] && break
  sleep 30
done
echo "=== GRIND COMPLETE ==="
