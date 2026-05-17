"""Fetch /alphas/{id} for the top-N rows in D0_MINING_REPORT.json and
print which IS checks pass/fail.

Run:
    python scripts/inspect_checks.py [N]
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"


def _load(p: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    fp = REPO / "D0_MINING_REPORT.json"
    if not fp.exists():
        print("no D0_MINING_REPORT.json"); return 1
    rows = json.loads(fp.read_text())
    ok = [r for r in rows if r.get("ok") and r.get("alpha_id")]
    ok.sort(key=lambda r: (-r.get("checks_passed", 0),
                            -r.get("sharpe", 0.0)))
    cm = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cmgr = cm.CredentialManager(base_path=str(REPO))
    if not cmgr.authenticate(auto_load=True, auto_prompt=False):
        print("auth failed"); return 2
    for r in ok[:n]:
        aid = r["alpha_id"]
        ra = cmgr.session.get(
            f"https://api.worldquantbrain.com/alphas/{aid}", timeout=30)
        if ra.status_code != 200:
            print(f"{aid}: HTTP {ra.status_code}"); continue
        ay = ra.json()
        isb = ay.get("is") or {}
        checks = isb.get("checks") or []
        s = r["settings"]
        print()
        print(f"=== {aid}  uni={s.get('universe')} delay={s.get('delay')} "
              f"decay={s.get('decay')} trunc={s.get('truncation')} "
              f"neut={s.get('neutralization')} ===")
        print(f"  expr: {r['optimized']}")
        print(f"  SH={isb.get('sharpe',0):+.3f} TO={isb.get('turnover',0):.3f} "
              f"FIT={isb.get('fitness',0):+.3f} "
              f"RET={isb.get('returns',0):+.4f} DD={isb.get('drawdown',0):.3f}")
        for c in checks:
            mark = "  " if c.get("result") == "PASS" else "x "
            lim = c.get("limit", "")
            val = c.get("value", "")
            print(f"  {mark}{c.get('name','?'):28} "
                  f"value={val} limit={lim} result={c.get('result','?')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
