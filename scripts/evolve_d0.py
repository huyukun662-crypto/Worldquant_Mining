#!/usr/bin/env python3
"""Evolutionary D0 alpha mining (Pareto + neighbourhood mutation).

End-to-end:
  1. Authenticate via credential.txt.
  2. Seed the archive: try to load WQ_D0_MINING_REPORT.json (prior dry-run
     results count as gen-0 evaluations) and/or generate `--seed-n` fresh
     random expressions at random settings.
  3. Generation loop: each round
       - Take top-K parents (Pareto front + score),
       - For each parent: M mutants (expression and/or settings),
       - Plus R fresh random expressions for exploration,
       - Submit all to WQ /simulations (sequential — single-account quota).
       - If any candidate passes the Submit-Alpha gate, immediately
         POST /alphas/{id}/submit and exit.
  4. Persist archive to WQ_D0_EVOLVE_REPORT.json after every submission.

Usage:
  python scripts/evolve_d0.py --seed-n 12 --gens 6 --parents 4 --muts 3 --rand 2
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import sys
import time
from dataclasses import asdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from mining_pipeline import wq_pipeline as wp
from mining_pipeline import d0_evolve as ev

log = logging.getLogger("evolve-d0")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")


def _result_to_cand(r: wp.WQResult) -> ev.Cand:
    return ev.Cand(expression=r.expression, settings=dict(r.settings),
                   sharpe=r.sharpe, turnover=r.turnover,
                   fitness=r.fitness, checks_passed=r.checks_passed,
                   checks_total=r.checks_total, alpha_id=r.alpha_id,
                   ok=r.ok, error=r.error)


def evaluate(session, expr: str, settings: dict) -> ev.Cand:
    res = wp.submit(session, expr, settings)
    c = _result_to_cand(res)
    if c.ok:
        log.info(f"      SH={c.sharpe:+.3f} TO={c.turnover:.3f} FIT={c.fitness:+.3f} "
                 f"chk={c.checks_passed}/{c.checks_total} score={c.score:+.3f}  alpha={c.alpha_id}")
    else:
        log.info(f"      ERR {c.error[:120]}")
    return c


def submit_alpha(session, alpha_id: str, poll_s: int = 300) -> dict:
    url = f"https://api.worldquantbrain.com/alphas/{alpha_id}/submit"
    log.info(f"submitting alpha {alpha_id} ...")
    r = session.post(url, timeout=30)
    if r.status_code not in (200, 201):
        return {"ok": False, "error": f"submit-{r.status_code}: {r.text[:300]}"}
    progress_url = r.headers.get("Location") or url
    t0 = time.time()
    last = None
    while time.time() - t0 < poll_s:
        time.sleep(5)
        rp = session.get(progress_url, timeout=30)
        if rp.status_code == 429:
            time.sleep(30); continue
        if rp.status_code not in (200, 201):
            continue
        try:
            data = rp.json()
        except Exception:
            continue
        last = data
        st = data.get("status", "")
        log.info(f"   submit status: {st}")
        if st in ("COMPLETE", "PENDING", "SUBMITTED"):
            return {"ok": True, "status": st, "data": data}
        if st in ("ERROR", "FAILED"):
            return {"ok": False, "error": f"submit-{st}: {data.get('message','')[:300]}",
                    "data": data}
    return {"ok": True, "status": "TIMEOUT-OK", "note": "polled out; check WQ UI",
            "data": last}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed-n", type=int, default=8,
                    help="Fresh random expressions to seed generation 0")
    ap.add_argument("--gens", type=int, default=6, help="Number of generations")
    ap.add_argument("--parents", type=int, default=4,
                    help="Parents picked from Pareto front each generation")
    ap.add_argument("--muts", type=int, default=3, help="Mutants per parent")
    ap.add_argument("--rand", type=int, default=2,
                    help="Fresh random expressions per generation (exploration)")
    ap.add_argument("--seed", type=int, default=4242)
    ap.add_argument("--archive-in", type=str, default="WQ_D0_MINING_REPORT.json",
                    help="Optional prior report to seed the archive")
    ap.add_argument("--out", type=str, default="WQ_D0_EVOLVE_REPORT.json")
    ap.add_argument("--submit-out", type=str, default="WQ_D0_SUBMISSION_RESULT.json")
    ap.add_argument("--no-submit", action="store_true")
    args = ap.parse_args()

    rng = random.Random(args.seed)

    cm_mod = wp._load(wp.VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")

    archive: list[ev.Cand] = []
    # Seed from prior report
    pri = REPO / args.archive_in
    if pri.exists():
        try:
            for d in json.load(open(pri)):
                if d.get("ok"):
                    archive.append(ev.Cand(
                        expression=d["expression"], settings=d["settings"],
                        sharpe=d["sharpe"], turnover=d["turnover"],
                        fitness=d["fitness"], checks_passed=d["checks_passed"],
                        checks_total=d["checks_total"],
                        alpha_id=d.get("alpha_id", ""), ok=True))
            log.info(f"seeded archive with {len(archive)} prior OK results from {pri}")
        except Exception as e:
            log.warning(f"could not seed from {pri}: {e}")

    def save():
        with open(args.out, "w") as f:
            json.dump([asdict(c) for c in archive], f, indent=2)

    save()

    def check_winner() -> ev.Cand | None:
        winners = [c for c in archive if c.passes_submit_gate]
        winners.sort(key=lambda c: c.fitness, reverse=True)
        return winners[0] if winners else None

    # Generation 0: SEED_EXPRS (structural priors) + a few fresh randoms.
    # Each seed is run at TWO setting variants (low-decay vs mid-decay) to
    # explore the small D0 settings space efficiently.
    log.info(f"=== gen 0: {len(ev.SEED_EXPRS)} seeds × 2 settings + "
             f"{args.seed_n} random")
    gen0: list[tuple[str, dict]] = []
    for s_expr in ev.SEED_EXPRS:
        gen0.append((s_expr, {"universe": "TOP3000", "delay": 0, "decay": 4,
                              "truncation": 0.01,
                              "neutralization": "SUBINDUSTRY",
                              "pasteurization": "ON"}))
        gen0.append((s_expr, {"universe": "TOP3000", "delay": 0, "decay": 1,
                              "truncation": 0.005,
                              "neutralization": "INDUSTRY",
                              "pasteurization": "ON"}))
    for _ in range(args.seed_n):
        gen0.append((ev.random_expr(rng), ev.random_settings(rng)))
    # Dedup
    seen = set()
    uniq: list[tuple[str, dict]] = []
    for e, s in gen0:
        key = e + json.dumps(s, sort_keys=True)
        if key in seen: continue
        seen.add(key); uniq.append((e, s))
    gen0 = uniq
    for i, (e, s) in enumerate(gen0, 1):
        log.info(f"  [gen0 {i}/{len(gen0)}] {e}")
        log.info(f"         settings={s}")
        c = evaluate(cm.session, e, s)
        archive.append(c)
        save()
        if c.passes_submit_gate:
            break

    w = check_winner()
    if w:
        log.info(f"gen0 winner: {w.alpha_id}  expr={w.expression}")
    else:
        # Subsequent generations
        for g in range(1, args.gens + 1):
            parents = ev.select_parents(archive, args.parents, rng)
            log.info(f"=== gen {g}: {len(parents)} parents (top score "
                     f"{parents[0].score:+.3f} if any)" if parents else
                     f"=== gen {g}: no parents — restarting from random")
            children: list[tuple[str, dict]] = []
            for p in parents:
                for _ in range(args.muts):
                    expr = ev.mutate(p.expression, rng)
                    sett = ev.mutate_settings(p.settings, rng)
                    children.append((expr, sett))
            for _ in range(args.rand):
                children.append((ev.random_expr(rng), ev.random_settings(rng)))
            # Dedup vs archive
            seen = {c.expression + json.dumps(c.settings, sort_keys=True)
                    for c in archive}
            children = [(e, s) for (e, s) in children
                        if (e + json.dumps(s, sort_keys=True)) not in seen]
            log.info(f"   {len(children)} unique children to evaluate")
            for i, (e, s) in enumerate(children, 1):
                log.info(f"   [g{g} {i}/{len(children)}] {e}")
                log.info(f"          settings={s}")
                c = evaluate(cm.session, e, s)
                archive.append(c)
                save()
                if c.passes_submit_gate:
                    log.info(f"   >>> SUBMIT-GATE PASSED at g{g} {i}: {c.alpha_id}")
                    break
            if check_winner():
                break

    # CSV export (mimics the spec's D0-mined-alphas-{date}.csv shape).
    import csv, datetime
    today = datetime.date.today().isoformat()
    csv_path = REPO / f"D0-mined-alphas-{today}.csv"
    csv_all = REPO / f"D0-mined-all-{today}.csv"
    fields = ["alpha_id", "expression", "universe", "delay", "decay",
              "truncation", "neutralization", "sharpe", "fitness", "turnover",
              "returns", "drawdown", "checks_passed", "checks_total", "status"]
    def _row(c):
        s = c.settings
        if not c.ok:
            status = "ERROR"
        elif c.passes_submit_gate:
            status = "PASSED"
        elif c.sharpe < ev.SHARPE_FLOOR:
            status = "FAILED_LOW_SHARPE"
        elif c.fitness < ev.FITNESS_FLOOR:
            status = "FAILED_LOW_FITNESS"
        elif c.turnover >= ev.TURNOVER_CEILING:
            status = "FAILED_HIGH_TURNOVER"
        else:
            status = "FAILED_CHECKS"
        return {"alpha_id": c.alpha_id, "expression": c.expression,
                "universe": s.get("universe"), "delay": s.get("delay"),
                "decay": s.get("decay"), "truncation": s.get("truncation"),
                "neutralization": s.get("neutralization"),
                "sharpe": c.sharpe, "fitness": c.fitness,
                "turnover": c.turnover, "returns": getattr(c, "returns", 0),
                "drawdown": getattr(c, "drawdown", 0),
                "checks_passed": c.checks_passed,
                "checks_total": c.checks_total, "status": status}
    with open(csv_all, "w", newline="", encoding="utf-8-sig") as f:
        w_csv = csv.DictWriter(f, fieldnames=fields)
        w_csv.writeheader()
        for c in archive:
            w_csv.writerow(_row(c))
    passed = [c for c in archive if c.passes_submit_gate]
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w_csv = csv.DictWriter(f, fieldnames=fields)
        w_csv.writeheader()
        for c in passed:
            w_csv.writerow(_row(c))
    log.info(f"wrote {csv_path} ({len(passed)} PASSED) and {csv_all} ({len(archive)} total)")

    w = check_winner()
    print("=" * 110)
    print(f"archive: {len(archive)}  OK: {sum(1 for c in archive if c.ok)}  "
          f"survivors: {sum(1 for c in archive if c.passes_submit_gate)}")
    if w:
        print(f"WINNER  SH={w.sharpe:+.3f} TO={w.turnover:.3f} FIT={w.fitness:+.3f} "
              f"chk={w.checks_passed}/{w.checks_total}")
        print(f"  alpha_id={w.alpha_id}")
        print(f"  expr   = {w.expression}")
        print(f"  setting= {w.settings}")
    else:
        # Show top 5 by score
        ok = sorted([c for c in archive if c.ok],
                    key=lambda c: c.score, reverse=True)[:5]
        print("top 5 by score:")
        for c in ok:
            print(f"  score={c.score:+.3f} SH={c.sharpe:+.3f} TO={c.turnover:.3f} "
                  f"FIT={c.fitness:+.3f} chk={c.checks_passed}/{c.checks_total}  "
                  f"{c.expression[:70]}")
    print("=" * 110)

    if not w:
        log.warning("no candidate passed the Submit-Alpha gate; nothing to submit")
        return 0
    if args.no_submit:
        log.info("--no-submit: stopping before /alphas/{id}/submit")
        return 0

    result = submit_alpha(cm.session, w.alpha_id)
    out = {
        "alpha_id": w.alpha_id,
        "expression": w.expression,
        "settings": w.settings,
        "is_metrics": {"sharpe": w.sharpe, "turnover": w.turnover,
                       "fitness": w.fitness,
                       "checks_passed": w.checks_passed,
                       "checks_total": w.checks_total},
        "submit": result,
    }
    with open(args.submit_out, "w") as f:
        json.dump(out, f, indent=2)
    log.info(f"wrote {args.submit_out}")
    print(json.dumps(out, indent=2))
    return 0 if result.get("ok") else 4


if __name__ == "__main__":
    sys.exit(main() or 0)
