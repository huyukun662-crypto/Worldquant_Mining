"""Agent 4 (Backtest Operator) — submit a batch of expressions to WQ
Brain with one fixed settings dict, persist results, and exit.

Usage:
    python scripts/run_batch.py logs/20260510_pv_leadlag_corr/expressions_batch_0001.json
"""

from __future__ import annotations

import importlib.util
import json
import logging
import sys
import time
from dataclasses import asdict
from pathlib import Path

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("agent4")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"


def _load(p: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main(batch_path: Path, out_path: Path) -> int:
    batch = json.loads(batch_path.read_text())
    expressions: list[str] = batch["expressions"]
    settings: dict = batch["settings"]
    log.info(f"loaded batch: {len(expressions)} expressions")
    for i, e in enumerate(expressions, 1):
        log.info(f"  [{i}] {e}")

    # auth with retry (same SSL race as elsewhere)
    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    auth_ok = False
    for attempt in range(6):
        if cm.authenticate(auto_load=True, auto_prompt=False):
            auth_ok = True
            break
        log.warning(f"auth attempt {attempt+1} failed; sleeping {2*(attempt+1)}s")
        time.sleep(2 * (attempt + 1))
    if not auth_ok:
        log.error("auth failed after retries"); return 2
    log.info(f"authenticated as {cm.credentials.username}")

    sys.path.insert(0, str(REPO))
    from mining_pipeline.wq_pipeline import submit  # noqa: E402

    results = []
    t0 = time.time()
    for i, expr in enumerate(expressions, 1):
        log.info(f"[{i}/{len(expressions)}] submit: {expr[:90]}")
        r = submit(cm.session, expr, settings)
        results.append(asdict(r))
        if r.ok:
            log.info(f"   WQ_SH={r.sharpe:+.3f} TO={r.turnover:.3f} "
                     f"FIT={r.fitness:+.3f} ckh={r.checks_passed}/{r.checks_total} "
                     f"alpha={r.alpha_id}")
        else:
            log.info(f"   [{r.error[:160]}]")
        out_path.write_text(json.dumps(
            {"settings": settings, "expressions": expressions,
             "results": results}, indent=2))
    elapsed = time.time() - t0
    log.info(f"batch done in {elapsed/60:.1f} min")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: run_batch.py <batch.json> [out.json]")
        sys.exit(1)
    bp = Path(sys.argv[1])
    op = Path(sys.argv[2]) if len(sys.argv) >= 3 else \
         bp.with_name(bp.stem.replace("expressions_", "backtest_results_") + ".json")
    sys.exit(main(bp, op))
