"""Submit flipped + smoothed forms of the top lean-scan picks."""
from __future__ import annotations
import importlib.util, json, sys, time
from dataclasses import asdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"

# Re-use the smart_d1_miner submit machinery
from mining_pipeline.lean_d1_miner import submit, FIXED_SETTINGS, _load


CANDIDATES = [
    # flip dflc_revere_idx (raw SH -1.51 FIT -1.54 TO 0.033)
    ("dflc_revere_idx_flip",
     "-rank(days_from_last_change(ts_backfill(pv13_revere_index_value, 60)))"),

    # flip gzs_custretsig (raw SH -1.67 FIT -0.92 TO 0.590)
    ("gzs_custretsig_flip",
     "-group_zscore(ts_backfill(pv13_custretsig_retsig, 60), sector)"),

    # smoothed gzs_custretsig: ts_mean(... 5) cuts turnover ~50% with
    # minor SH loss - should push FIT past 1.0 if math holds
    ("gzs_custretsig_flip_smooth5",
     "-rank(ts_mean(group_zscore(ts_backfill(pv13_custretsig_retsig, 60), sector), 5))"),

    # heavier smoothing variant
    ("gzs_custretsig_flip_smooth10",
     "-rank(ts_mean(group_zscore(ts_backfill(pv13_custretsig_retsig, 60), sector), 10))"),
]


def main():
    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    assert cm.authenticate(auto_load=True, auto_prompt=False)
    print(f"authenticated as {cm.credentials.username}")

    out_path = REPO / "WQ_D1_LEAN_FOLLOWUP.json"
    results = []
    for i, (tag, expr) in enumerate(CANDIDATES, 1):
        print(f"=== followup {i}/{len(CANDIDATES)} [{tag}]")
        print(f"   expr: {expr}")
        r = submit(cm.session, expr, FIXED_SETTINGS)
        r.tag = tag
        if r.ok:
            print(f"   SH={r.sharpe:+.3f} TO={r.turnover:.3f} FIT={r.fitness:+.3f} "
                  f"pass={r.all_checks_pass} ({r.checks_passed}/{r.checks_total}) "
                  f"alpha={r.alpha_id}")
        else:
            print(f"   ERR: {r.error[:160]}")
        results.append(r)
        out_path.write_text(json.dumps([asdict(x) for x in results], indent=2))


if __name__ == "__main__":
    main()
