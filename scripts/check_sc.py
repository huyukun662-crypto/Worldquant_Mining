"""Poll self-correlation for a given alpha_id until WQ computes it."""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mine_cold_fields import (fetch_self_corr, _load, VENDOR, REPO, log)

if len(sys.argv) < 2:
    print("usage: check_sc.py <alpha_id> [timeout_s]")
    sys.exit(1)
aid = sys.argv[1]
timeout = int(sys.argv[2]) if len(sys.argv) > 2 else 300

cm = _load(VENDOR/"core"/"credential_manager.py","cm").CredentialManager(base_path=str(REPO))
cm.authenticate(auto_load=True, auto_prompt=False)

t0 = time.time()
while time.time() - t0 < timeout:
    sc, top, status = fetch_self_corr(cm.session, aid, timeout_s=60)
    print(f"  alpha={aid}  sc={sc}  status={status}")
    if sc is not None:
        print(f"\nself_corr = {sc}")
        if abs(sc) < 0.7:
            print("✅ PASS (|sc| < 0.7)")
        else:
            print(f"❌ FAIL (|sc| = {abs(sc):.3f} >= 0.7)")
        break
    time.sleep(20)
else:
    print(f"\n⏳ timeout after {timeout}s -- still PENDING")
