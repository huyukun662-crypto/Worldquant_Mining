"""Tune queued alphas to a SUBMITTABLE configuration.

Reads a TUNE_QUEUE text dump (the IQC tuning queue), and for each selected
alpha runs an Optuna search over SIMULATION SETTINGS ONLY
(delay, decay, neutralization, truncation, universe) - the expression logic
is left untouched - submitting each trial to WQ Brain `/simulations` and
keeping the configuration where every non-PENDING IS check PASSes
(submittable).

Why settings-only: changing decay/neutralization/truncation/universe is the
safe "tune to submittable" lever; it cannot break the expression's intent the
way rewriting integer windows can. SELF_CORRELATION is PENDING in simulation
(resolves only at real submit), so alphas that fail *only* self-correlation
cannot be fixed here and are reported as such.

Usage:
    python scripts/tune_queue.py TUNE_QUEUE_alpha.txt \
        --top 8 --trials 6 --skip-iv --out TUNE_QUEUE_RESULTS.json
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import re
import sys
from dataclasses import asdict
from pathlib import Path

import optuna

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("tune-queue")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"

# reuse the hardened submit/poll/checks machinery + submittability test
sys.path.insert(0, str(REPO))
from mining_pipeline.agent_workflow import (  # noqa: E402
    SimulatorAgent, _submittable, IV_PATTERN, FIXED_SETTINGS,
)

# Settings search space for "tune to submittable".
TUNE_SPACE = {
    "delay":          [0, 1],
    "decay":          [0, 4, 8, 12, 20, 30, 64],
    "neutralization": ["INDUSTRY", "SUBINDUSTRY", "SECTOR", "MARKET"],
    "truncation":     [0.02, 0.05, 0.08, 0.10],
    "universe":       ["TOP3000", "TOP1000", "TOP500"],
    "pasteurization": ["ON"],
}

GATE_FAILS = {"LOW_SHARPE", "LOW_FITNESS", "LOW_SUB_UNIVERSE_SHARPE",
              "CONCENTRATED_WEIGHT", "HIGH_TURNOVER", "LOW_TURNOVER"}


def _load(p: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def parse_queue(path: Path) -> list[dict]:
    """Parse the TUNE_QUEUE text dump into structured alpha records."""
    text = path.read_text(encoding="utf-8")
    blocks = re.split(r"\nAlpha ID:\s*", text)
    out = []
    for b in blocks[1:]:
        aid = b.splitlines()[0].strip()
        gain = re.search(r"加分\s*(-?\d+)", b)
        selfc = re.search(r"Self-Correlation[^:]*:\s*(\w+)", b)
        other = re.search(r"其他 FAIL:\s*(.+)", b)
        st = re.search(r"设置:\s*USA/(\w+),\s*Delay=(\d+),\s*Decay=(\d+),"
                       r"\s*Neutralization=(\w+),\s*Truncation=([\d.]+)", b)
        # expression: lines after "Alpha:" until blank line / end
        m = re.search(r"\nAlpha:\s*\n(.*?)(?:\n\s*\n|\Z)", b, re.S)
        expr = ""
        if m:
            lines = [ln for ln in m.group(1).splitlines()
                     if ln.strip() and not ln.strip().startswith("#")]
            expr = " ".join(ln.strip() for ln in lines)
        fails = []
        if other and other.group(1).strip() not in ("无", ""):
            fails = [x.strip() for x in re.split(r"[,，]", other.group(1)) if x.strip()]
        out.append({
            "alpha_id": aid,
            "score_gain": int(gain.group(1)) if gain else 0,
            "self_corr": selfc.group(1) if selfc else "",
            "other_fails": fails,
            "base": {
                "universe": st.group(1) if st else "TOP3000",
                "delay": int(st.group(2)) if st else 1,
                "decay": int(st.group(3)) if st else 0,
                "neutralization": st.group(4) if st else "INDUSTRY",
                "truncation": float(st.group(5)) if st else 0.08,
            } if st else {},
            "expression": expr,
            "uses_iv": bool(IV_PATTERN.search(expr)),
        })
    return out


def tune_one(sim: SimulatorAgent, alpha: dict, n_trials: int, seed: int) -> dict:
    expr = alpha["expression"]
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    study = optuna.create_study(direction="maximize",
                                sampler=optuna.samplers.TPESampler(seed=seed))
    trials = []

    def objective(trial):
        settings = {k: trial.suggest_categorical(k, v) for k, v in TUNE_SPACE.items()}
        log.info(f"   [{alpha['alpha_id']}] d={settings['delay']} dec={settings['decay']} "
                 f"neut={settings['neutralization']} tr={settings['truncation']} u={settings['universe']}")
        try:
            res = sim.submit(expr, settings)
        except Exception as e:
            log.warning(f"      exc {type(e).__name__}"); return -5.0
        rec = {"settings": res.settings, "ok": res.ok, "sharpe": res.sharpe,
               "turnover": res.turnover, "fitness": res.fitness,
               "drawdown": res.drawdown, "submittable": res.submittable,
               "checks_passed": res.checks_passed, "checks_total": res.checks_total,
               "alpha_id": res.alpha_id, "error": res.error,
               "fails": [c["name"] for c in res.checks
                         if c.get("result") not in ("PASS", "PENDING")]}
        trials.append(rec)
        if not res.ok:
            log.info(f"      [{res.error[:70]}]"); return -5.0
        mark = "SUBMITTABLE" if res.submittable else f"{res.checks_passed}/{res.checks_total}"
        log.info(f"      SH={res.sharpe:+.2f} TO={res.turnover:.3f} FIT={res.fitness:+.2f} "
                 f"DD={res.drawdown:.3f} [{mark}] fails={rec['fails']}")
        score = min(res.sharpe, 1.25) / 1.25 + min(res.fitness, 1.0) / 1.0
        if res.submittable:
            score += 2.0
        return score

    study.optimize(objective, n_trials=n_trials)
    subs = [t for t in trials if t.get("submittable") and t["sharpe"] >= 1.25
            and t["fitness"] >= 1.0]
    subs.sort(key=lambda t: t["fitness"] + 0.3 * t["sharpe"], reverse=True)
    best = subs[0] if subs else max(
        (t for t in trials if t.get("ok")),
        key=lambda t: min(t["sharpe"], 1.25) / 1.25 + min(t["fitness"], 1.0),
        default=None)
    return {"alpha_id": alpha["alpha_id"], "score_gain": alpha["score_gain"],
            "expression": expr, "uses_iv": alpha["uses_iv"],
            "became_submittable": bool(subs), "best": best, "all_trials": trials}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("queue", help="TUNE_QUEUE text file")
    ap.add_argument("--top", type=int, default=8, help="how many alphas to tune")
    ap.add_argument("--trials", type=int, default=6, help="settings trials per alpha")
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--skip-iv", action="store_true", help="skip alphas that use IV fields")
    ap.add_argument("--only", default=None, help="comma-separated alpha_ids to tune")
    ap.add_argument("--out", default="TUNE_QUEUE_RESULTS.json")
    args = ap.parse_args()

    alphas = parse_queue(Path(args.queue))
    log.info(f"parsed {len(alphas)} alphas from {args.queue}")

    if args.only:
        ids = set(x.strip() for x in args.only.split(","))
        targets = [a for a in alphas if a["alpha_id"] in ids]
    else:
        # gate-failing alphas (settings-tuning can plausibly fix), best 加分 first
        targets = [a for a in alphas
                   if set(a["other_fails"]) & GATE_FAILS
                   and (not args.skip_iv or not a["uses_iv"])]
        targets.sort(key=lambda a: a["score_gain"], reverse=True)
        targets = targets[:args.top]

    self_only = [a for a in alphas if a["self_corr"] == "FAIL" and not a["other_fails"]]
    log.info(f"tuning {len(targets)} gate-failing alphas; "
             f"{len(self_only)} alphas fail ONLY self-correlation (not settings-fixable)")
    for a in targets:
        log.info(f"   target +{a['score_gain']:<4} {a['alpha_id']} "
                 f"fails={a['other_fails']} iv={a['uses_iv']}")

    cm = _load(VENDOR / "core" / "credential_manager.py", "cm").CredentialManager(
        base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("auth failed"); return 2
    sim = SimulatorAgent(cm.session)

    results = []
    for i, a in enumerate(targets, 1):
        log.info(f"=== [{i}/{len(targets)}] tuning {a['alpha_id']} (+{a['score_gain']}) ===")
        r = tune_one(sim, a, args.trials, args.seed + i)
        results.append(r)
        json.dump({"tuned": results,
                   "self_correlation_only": [a["alpha_id"] for a in self_only]},
                  open(args.out, "w"), indent=2)

    print("\n" + "=" * 100)
    won = [r for r in results if r["became_submittable"]]
    print(f"tuned {len(results)} alphas -> {len(won)} reached SUBMITTABLE\n")
    print(f"{'gain':>5} {'alpha':<10}{'sub?':<6}{'SH':>6}{'TO':>7}{'FIT':>6}{'DD':>7}  best settings")
    for r in sorted(results, key=lambda r: (r["became_submittable"], r["score_gain"]), reverse=True):
        b = r["best"] or {}
        s = b.get("settings", {})
        cfg = (f"d{s.get('delay')} dec{s.get('decay')} {s.get('neutralization','')[:6]} "
               f"tr{s.get('truncation')} {s.get('universe','')}" if s else "-")
        print(f"{r['score_gain']:>5} {r['alpha_id']:<10}"
              f"{'YES' if r['became_submittable'] else 'no':<6}"
              f"{b.get('sharpe',0):6.2f}{b.get('turnover',0):7.3f}{b.get('fitness',0):6.2f}"
              f"{b.get('drawdown',0):7.3f}  {cfg}")
    print("=" * 100)
    log.info(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
