"""Submit single alpha 1YoOqNvz to WQ Brain — gamble on it being accepted
despite LOW_SHARPE/LOW_SUB checks failing in the simulation report.

Fetches current /alphas/{id} state first to show all 8 checks (some
correlation checks are async and may have updated since simulation),
then calls POST /alphas/{id}/submit.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ALPHA_ID = sys.argv[1] if len(sys.argv) > 1 else "1YoOqNvz"

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"


def _load(p, name):
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        print("AUTH FAIL"); return 2
    session = cm.session
    print(f"authenticated as {cm.credentials.username}")
    print(f"alpha_id: {ALPHA_ID}")
    print()

    print("=" * 70)
    print(f"GET /alphas/{ALPHA_ID}")
    print("=" * 70)
    ra = session.get(f"https://api.worldquantbrain.com/alphas/{ALPHA_ID}",
                      timeout=30)
    if ra.status_code != 200:
        print(f"  status={ra.status_code} body={ra.text[:500]}")
        return 1
    alpha = ra.json()
    is_ = alpha.get("is", {}) or {}
    os_ = alpha.get("os", {}) or {}
    print(f"  IS: sharpe={is_.get('sharpe')} fitness={is_.get('fitness')} "
          f"turnover={is_.get('turnover')} returns={is_.get('returns')} "
          f"drawdown={is_.get('drawdown')}")
    print(f"  OS: sharpe={os_.get('sharpe')} fitness={os_.get('fitness')} "
          f"turnover={os_.get('turnover')}")
    print(f"  status: {alpha.get('status')}  grade: {alpha.get('grade')}")
    print(f"  checks (IS):")
    for c in (is_.get("checks") or []):
        print(f"    {c.get('name'):>32}  {c.get('result'):>6}  "
              f"limit={c.get('limit')}  value={c.get('value')}")
    print(f"  checks (OS):")
    for c in (os_.get("checks") or []):
        print(f"    {c.get('name'):>32}  {c.get('result'):>6}  "
              f"limit={c.get('limit')}  value={c.get('value')}")

    print()
    print("=" * 70)
    print(f"POST /alphas/{ALPHA_ID}/submit")
    print("=" * 70)
    rs = session.post(
        f"https://api.worldquantbrain.com/alphas/{ALPHA_ID}/submit", timeout=30)
    print(f"  status={rs.status_code}")
    print(f"  body={rs.text[:2000]}")
    print()

    # Re-fetch after submit
    print("=" * 70)
    print(f"GET /alphas/{ALPHA_ID} (after submit)")
    print("=" * 70)
    ra2 = session.get(f"https://api.worldquantbrain.com/alphas/{ALPHA_ID}",
                       timeout=30)
    if ra2.status_code == 200:
        alpha2 = ra2.json()
        print(f"  status: {alpha2.get('status')}  grade: {alpha2.get('grade')}")
        print(f"  full: {json.dumps(alpha2, indent=2)[:2000]}")

    out = REPO / f"WQ_SUBMIT_GAMBLE_{ALPHA_ID}.json"
    with open(out, "w") as f:
        json.dump({"pre": alpha, "submit_status": rs.status_code,
                   "submit_body": rs.text,
                   "post": ra2.json() if ra2.status_code == 200 else None},
                  f, indent=2)
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
