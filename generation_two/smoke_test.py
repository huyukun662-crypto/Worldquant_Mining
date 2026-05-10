"""Smoke test: authenticate and run a couple of WQ Brain simulations against
USA TOP3000, end-to-end, without entering the continuous-evolution loop.

Usage:
    python -m generation_two.smoke_test
"""

from __future__ import annotations

import logging
import os
import sys
import time

# Allow `python -m generation_two.smoke_test` from the repo root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generation_two.core.credential_manager import CredentialManager
from generation_two.core.simulator_tester import SimulatorTester, SimulationSettings


ALPHAS = [
    "group_neutralize(ts_zscore(operating_income / sales, 60), subindustry)",
    "group_neutralize(-ts_rank(close / ts_mean(close, 20), 30), subindustry)",
]


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    here = os.path.dirname(os.path.abspath(__file__))
    cm = CredentialManager(base_path=here)
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        logging.error("Authentication failed")
        return 1

    sess = cm.get_session()
    logging.info("Connected to WQ Brain")

    region_configs = {
        "USA": type(
            "RegionConfig",
            (),
            {"region": "USA", "universe": "TOP3000", "delay": 1},
        )()
    }
    tester = SimulatorTester(session=sess, region_configs=region_configs)

    settings = SimulationSettings(
        region="USA",
        testPeriod="P5Y0M0D",
        neutralization="INDUSTRY",
        truncation=0.08,
    )

    futures = []
    for expr in ALPHAS:
        logging.info("Submitting: %s", expr)
        futures.append(tester.simulate_template_concurrent(expr, "USA", settings))
        time.sleep(0.3)

    results = tester.wait_for_results(futures, timeout=600)

    print("\n=== smoke test results ===")
    for r in results:
        if r.success:
            print(
                f"OK   sharpe={r.sharpe:+.3f} fitness={r.fitness:+.3f} "
                f"turnover={r.turnover:.2f} returns={r.returns:+.4f} | {r.template[:90]}"
            )
        else:
            print(f"FAIL {r.error_message[:160]} | {r.template[:90]}")
    print("===========================")
    return 0 if any(r.success for r in results) else 2


if __name__ == "__main__":
    sys.exit(main())
