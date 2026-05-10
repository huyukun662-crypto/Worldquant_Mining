"""Stage 2.5 — settings-grid tuner for a single alpha expression.

The *expression* must come from a non-RP source (anything our screener
already produced is fine), but per WorldQuant Brain rules the *simulation
settings* are tunable. This script grids over

    decay × truncation × universe × neutralization

(plus an optional `nanHandling` knob), runs each combo on the official
IS window 2019-01-01..2023-12-31 with slot saturation, and reports the
best configuration that satisfies the same hard gate as the screener::

        IS Sharpe > 1.25  AND  IS Turnover < 0.25

Usage::

    python -m generation_two.tune_settings \
        --expr 'group_neutralize(ts_decay_linear(-ts_rank(returns, 252), 60), subindustry)' \
        --slots 3
"""

from __future__ import annotations

import argparse
import itertools
import json
import logging
import os
import sys
import time
from dataclasses import asdict, dataclass

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generation_two.core.credential_manager import CredentialManager
from generation_two.core.simulator_tester import (
    SimulationResult,
    SimulationSettings,
    SimulatorTester,
)


IS_START = "2019-01-01"
IS_END = "2023-12-31"
MIN_SHARPE = 1.25
MAX_TURNOVER = 0.25


# Tunable axes.  delay=0 is *preferred* per the user's brief, but this WQ
# Brain account currently lacks the entitlement (the API returns
# "Delay 0 is not available." HTTP 400). We still emit delay=0 trials so
# that the grid is honest about what was attempted; combos that get
# rejected at submit time are recorded with error="delay-not-available"
# and excluded from the qualifier set.
DELAY_GRID = [0, 1]
DECAY_GRID = [0, 4, 8]
TRUNCATION_GRID = [0.05, 0.08]
UNIVERSE_GRID = ["TOP3000", "TOP2000"]
NEUTRALIZATION_GRID = ["INDUSTRY", "SUBINDUSTRY"]


@dataclass
class SettingsTrial:
    delay: int
    decay: int
    truncation: float
    universe: str
    neutralization: str
    success: bool
    sharpe: float
    turnover: float
    fitness: float
    error: str = ""

    def passes(self) -> bool:
        return (
            self.success
            and self.sharpe == self.sharpe
            and self.sharpe > MIN_SHARPE
            and self.turnover < MAX_TURNOVER
        )

    def label(self) -> str:
        return (
            f"delay={self.delay} d={self.decay} t={self.truncation:.2f} "
            f"u={self.universe} n={self.neutralization}"
        )


def _build_combos() -> list[dict]:
    combos = []
    # Order delay=0 first so the preferred combos are submitted first; if
    # the account doesn't have delay=0 entitlement they all fail fast and
    # the grid moves on to delay=1 without blocking slots.
    for delay, decay, trunc, uni, neu in itertools.product(
        DELAY_GRID, DECAY_GRID, TRUNCATION_GRID, UNIVERSE_GRID, NEUTRALIZATION_GRID
    ):
        combos.append({
            "delay": delay,
            "decay": decay,
            "truncation": trunc,
            "universe": uni,
            "neutralization": neu,
        })
    return combos


def _settings(combo: dict) -> SimulationSettings:
    return SimulationSettings(
        region="USA",
        universe=combo["universe"],
        delay=combo["delay"],
        decay=combo["decay"],
        neutralization=combo["neutralization"],
        truncation=combo["truncation"],
        startDate=IS_START,
        endDate=IS_END,
    )


def _record(combo: dict, res: SimulationResult | None) -> SettingsTrial:
    if res is None:
        return SettingsTrial(
            delay=combo["delay"], decay=combo["decay"], truncation=combo["truncation"],
            universe=combo["universe"], neutralization=combo["neutralization"],
            success=False, sharpe=0.0, turnover=0.0, fitness=0.0,
            error="no-result",
        )
    return SettingsTrial(
        delay=combo["delay"], decay=combo["decay"], truncation=combo["truncation"],
        universe=combo["universe"], neutralization=combo["neutralization"],
        success=bool(res.success),
        sharpe=float(res.sharpe or 0.0),
        turnover=float(res.turnover or 0.0),
        fitness=float(res.fitness or 0.0),
        error=res.error_message or "",
    )


def _probe_delay_0(sess) -> bool:
    """Send a tiny no-op simulation with delay=0 to see if the account has
    the entitlement. Returns True if HTTP 201 (queued); False on the
    'Delay 0 is not available.' rejection or any other error.
    """
    payload = {
        "type": "REGULAR",
        "settings": {
            "instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000",
            "delay": 0, "decay": 0, "neutralization": "INDUSTRY",
            "truncation": 0.08, "pasteurization": "ON", "unitHandling": "VERIFY",
            "nanHandling": "OFF", "language": "FASTEXPR", "visualization": False,
            "startDate": IS_START, "endDate": IS_END,
        },
        "regular": "rank(close)",
    }
    try:
        r = sess.post("https://api.worldquantbrain.com/simulations",
                      json=payload, timeout=15)
        if r.status_code == 201:
            return True
        logging.warning("delay=0 probe got %d: %s", r.status_code, r.text[:140])
    except Exception as e:
        logging.warning("delay=0 probe failed: %s", e)
    return False


def grid_search(
    expr: str,
    *,
    slots: int = 3,
    submit_retry_delay: float = 4.0,
    submit_retry_max: int = 30,
    timeout_per_sim: int = 600,
) -> list[SettingsTrial]:
    cm = CredentialManager(base_path=os.path.dirname(os.path.abspath(__file__)))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        raise RuntimeError("WQ Brain authentication failed")
    sess = cm.get_session()

    region_configs = {}
    for u in UNIVERSE_GRID:
        region_configs.setdefault("USA", type(
            "RegionConfig",
            (),
            {"region": "USA", "universe": "TOP3000", "delay": 1},
        )())
    tester = SimulatorTester(session=sess, region_configs=region_configs)

    combos = _build_combos()
    # Filter combos by entitlement. We probe delay=0 once; if the account
    # doesn't have it, the delay=0 combos are recorded as
    # error="delay-not-available" rather than wasting submit retries.
    has_delay_0 = _probe_delay_0(sess)
    if not has_delay_0:
        logging.warning(
            "❌ Account lacks delay=0 entitlement; %d combos skipped",
            sum(1 for c in combos if c["delay"] == 0)
        )
    in_flight: dict = {}
    pending = list(combos)
    results: list[SettingsTrial] = []

    def fill_slots():
        while pending and len(in_flight) < slots:
            combo = pending.pop(0)
            # Skip delay=0 combos when the account lacks the entitlement.
            if combo["delay"] == 0 and not has_delay_0:
                results.append(SettingsTrial(
                    delay=combo["delay"], decay=combo["decay"],
                    truncation=combo["truncation"], universe=combo["universe"],
                    neutralization=combo["neutralization"],
                    success=False, sharpe=0.0, turnover=0.0, fitness=0.0,
                    error="delay-not-available",
                ))
                continue
            settings = _settings(combo)
            for attempt in range(submit_retry_max):
                # Override region universe per combo (settings.universe is sent
                # in the payload, but submit_simulation also reads
                # region_configs[region].universe — so we point it at the
                # combo's universe before submitting).
                tester.region_configs["USA"].universe = combo["universe"]
                progress_url = tester.submit_simulation(expr, "USA", settings)
                if progress_url:
                    fut = tester.executor.submit(
                        tester.monitor_simulation, progress_url, expr, "USA", settings
                    )
                    in_flight[fut] = combo
                    logging.info(
                        "🚀 [in-flight=%d/%d] %s",
                        len(in_flight), slots,
                        f"d={combo['decay']} t={combo['truncation']:.2f} "
                        f"u={combo['universe']} n={combo['neutralization']}"
                    )
                    break
                time.sleep(submit_retry_delay)
            else:
                logging.error("Submit retries exhausted for combo=%s", combo)
                results.append(SettingsTrial(
                    delay=combo["delay"], decay=combo["decay"],
                    truncation=combo["truncation"], universe=combo["universe"],
                    neutralization=combo["neutralization"],
                    success=False, sharpe=0.0, turnover=0.0, fitness=0.0,
                    error="submit-retry-exhausted",
                ))

    fill_slots()
    while in_flight:
        done = [f for f in list(in_flight.keys()) if f.done()]
        if not done:
            time.sleep(2.0)
            continue
        for fut in done:
            combo = in_flight.pop(fut)
            try:
                res = fut.result(timeout=timeout_per_sim)
            except Exception as e:
                logging.warning("future error %s: %s", combo, e)
                res = None
            trial = _record(combo, res)
            tag = "PASS" if trial.passes() else "fail"
            logging.info(
                "✅ %s | sharpe=%+.3f turn=%.3f fitness=%+.3f | %s",
                tag, trial.sharpe, trial.turnover, trial.fitness, trial.label()
            )
            results.append(trial)
        fill_slots()

    return results


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--expr", required=True, help="Alpha expression (no $-placeholders)")
    p.add_argument("--slots", type=int, default=3)
    p.add_argument("--out", default="settings_tuning.json")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    combos = _build_combos()
    logging.info(
        "Settings grid: %d combos = %d decay × %d trunc × %d universe × %d neu (slots=%d)",
        len(combos), len(DECAY_GRID), len(TRUNCATION_GRID),
        len(UNIVERSE_GRID), len(NEUTRALIZATION_GRID), args.slots,
    )
    logging.info("expr: %s", args.expr)

    trials = grid_search(args.expr, slots=args.slots)

    qualifiers = [t for t in trials if t.passes()]
    qualifiers.sort(key=lambda t: t.sharpe, reverse=True)

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), args.out)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "expr": args.expr,
            "qualifiers": [asdict(t) for t in qualifiers],
            "all_trials": [asdict(t) for t in trials],
        }, f, ensure_ascii=False, indent=2)

    print("\n=== Settings tuning summary ===")
    print(f"expr        : {args.expr}")
    print(f"trials      : {len(trials)}")
    print(f"sim-fail    : {sum(1 for t in trials if not t.success)}")
    print(f"qualifiers  : {len(qualifiers)}  (Sharpe>{MIN_SHARPE} AND turn<{MAX_TURNOVER})")
    if qualifiers:
        print("\nTop qualifiers:")
        for t in qualifiers[:10]:
            print(f"  Sharpe={t.sharpe:+.3f} turn={t.turnover:.3f} | {t.label()}")
        winner = qualifiers[0]
        print(f"\n🏆 Best: Sharpe={winner.sharpe:+.3f} turn={winner.turnover:.3f}")
        print(f"    decay={winner.decay} truncation={winner.truncation} "
              f"universe={winner.universe} neutralization={winner.neutralization}")
    print(f"\nwritten to  : {out_path}")
    print("================================")
    return 0


if __name__ == "__main__":
    sys.exit(main())
