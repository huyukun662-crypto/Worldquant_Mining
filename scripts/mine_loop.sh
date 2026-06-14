#!/bin/bash
# Session loop: repeatedly run the guarded auto-miner. Emits ONE status line per
# round (probe latency + outcome). Stops when a SH>1.5 PASS-ALL sibling is found.
# Quota-safe: during congestion only the cheap probe runs; the batch fires only
# in a fast window. Run via a persistent Monitor so each line wakes the session.
cd /home/user/Worldquant_Mining
round=0
while true; do
  round=$((round+1))
  line=$(bash scripts/auto_mine.sh 2>/dev/null | grep -E "PROBE|FOUND|CONGESTED|FAST WINDOW|SH=" | tr '\n' ' ')
  echo "ROUND $round $(date -u +%H:%M:%S) :: $line"
  if [ -f SIBLING_FOUND.json ]; then
    echo "SIBLING_FOUND -- stopping loop"
    break
  fi
  sleep 840
done
