"""Resume cross-family: skip pairs already done in WQ_D1_CROSS.json."""
from __future__ import annotations
import json
import logging
from dataclasses import asdict
from itertools import combinations
from pathlib import Path

from mining_pipeline.cross_family import CHAMPIONS
from mining_pipeline.diversify_d1_miner import BASE_SETTINGS, submit, _load, VENDOR

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("cross-resume")

REPO = Path(__file__).resolve().parent.parent


def main():
    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    assert cm.authenticate(auto_load=True, auto_prompt=False)
    log.info(f"authenticated as {cm.credentials.username}")

    out_path = REPO / "WQ_D1_CROSS.json"
    results = json.loads(out_path.read_text()) if out_path.exists() else []
    done_tags = {r.get("tag", "") for r in results if r.get("ok")}
    log.info(f"already done: {sorted(done_tags)}")

    keys = list(CHAMPIONS.keys())
    pairs = list(combinations(keys, 2))
    remaining = []
    for a, b in pairs:
        tag = f"{a[:1]}_x_{b[:1]}"
        if tag not in done_tags:
            remaining.append((tag, a, b))
    log.info(f"remaining: {len(remaining)} pairs")

    for i, (tag, a, b) in enumerate(remaining, 1):
        expr = f"rank(({CHAMPIONS[a]}) + ({CHAMPIONS[b]}))"
        log.info(f"=== resume {i}/{len(remaining)} [{tag}] = {a} × {b}")
        r = submit(cm.session, expr, BASE_SETTINGS)
        r.tag = tag
        if r.ok:
            log.info(f"   SH={r.sharpe:+.3f} TO={r.turnover:.3f} FIT={r.fitness:+.3f} "
                     f"pass={r.all_checks_pass} alpha={r.alpha_id}")
        else:
            log.info(f"   ERR: {r.error[:160]}")
        results.append(asdict(r) if hasattr(r, '__dict__') else r)
        out_path.write_text(json.dumps([
            asdict(x) if hasattr(x, '__dict__') else x for x in results
        ], indent=2))


if __name__ == "__main__":
    main()
