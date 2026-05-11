"""Iterative miner: run multiple expression batches against WQ Brain
until N distinct-skeleton survivors meet WQ thresholds.

Each batch is a JSON of the form:

    {
      "mechanism": "<name>",
      "settings": { ... full WQ settings dict ... },
      "expressions": [ "<wq-fast-expression>", ... ]   # length 8 per workflow
    }

Behaviour:
- Loop over batch files in lexicographic order.
- For each batch: authenticate (with retry), submit each expression with
  the batch's settings, persist results to disk after each submission.
- After each batch, count distinct-skeleton survivors (WQ_SH > 1.25,
  TO < 0.25) across ALL prior results. Exit when >= target_k.
- Final survivor digest written to <session>/outputs/survivors.json.

Run:
    python -m mining_pipeline.iter_mine \
        --session logs/20260510_pv_leadlag_corr \
        --target-k 4 \
        --max-batches 8

This is the controller for the user's mandate "持续挖 挖到有4个结构不同
且满足条件的为止".
"""

from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import logging
import sys
import time
from dataclasses import asdict
from pathlib import Path

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("iter-mine")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"

WQ_SHARPE_FLOOR = 1.25
WQ_TURNOVER_CEILING = 0.25


def _load(p: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# Skeleton fingerprint — same definition as extract_uncorrelated.skeleton,
# but with fewer field tokens so cap/sharesout/adv20 collapse to X.
_FIELD_TOKENS = {
    "open", "high", "low", "close", "volume", "vwap", "returns",
    "dollar_volume", "cap", "sharesout",
    "adv5", "adv10", "adv20", "adv30", "adv60", "adv120",
}


def skeleton(expr: str) -> str:
    tree = ast.parse(expr, mode="eval").body

    def walk(node) -> str:
        if isinstance(node, ast.Constant):
            return "D"
        if isinstance(node, ast.Name):
            return "X" if node.id in _FIELD_TOKENS else node.id
        if isinstance(node, ast.UnaryOp):
            return f"u{type(node.op).__name__}({walk(node.operand)})"
        if isinstance(node, ast.BinOp):
            return f"b{type(node.op).__name__}({walk(node.left)},{walk(node.right)})"
        if isinstance(node, ast.Call):
            return f"{node.func.id}({','.join(walk(a) for a in node.args)})"
        raise ValueError(f"unsupported node: {type(node).__name__}")
    return walk(tree)


def load_prior_results(session_dir: Path) -> list[dict]:
    """Load all prior `backtest_results_*.json` from the session folder."""
    out: list[dict] = []
    for p in sorted(session_dir.glob("backtest_results_*.json")):
        try:
            data = json.loads(p.read_text())
            for r in data.get("results", []):
                r["_source"] = p.name
                out.append(r)
        except Exception:
            continue
    return out


def survivors(all_results: list[dict]) -> list[dict]:
    """Distinct-skeleton candidates meeting WQ thresholds, sorted by WQ_SH."""
    ok = [r for r in all_results
          if r.get("ok") and r.get("sharpe", 0.0) > WQ_SHARPE_FLOOR
          and r.get("turnover", 1.0) < WQ_TURNOVER_CEILING]
    ok.sort(key=lambda r: r["sharpe"], reverse=True)
    picked: list[dict] = []
    used: set[str] = set()
    for r in ok:
        try:
            sk = skeleton(r["expression"])
        except Exception:
            continue
        if sk in used:
            continue
        used.add(sk)
        picked.append({**r, "skeleton": sk})
    return picked


def authenticate():
    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    for attempt in range(6):
        if cm.authenticate(auto_load=True, auto_prompt=False):
            return cm
        log.warning(f"auth attempt {attempt+1} failed; sleeping {2*(attempt+1)}s")
        time.sleep(2 * (attempt + 1))
    raise RuntimeError("auth failed after retries")


def run_batch(session_dir: Path, batch_path: Path, cm) -> Path:
    sys.path.insert(0, str(REPO))
    from mining_pipeline.wq_pipeline import submit  # noqa: E402

    batch = json.loads(batch_path.read_text())
    mech: str = batch.get("mechanism", batch_path.stem)
    expressions_raw = batch.get("expressions", [])
    per_expr_settings = bool(batch.get("settings_per_expression"))
    base_settings: dict = batch.get("settings", {})

    if per_expr_settings:
        # `expressions` is a list of {expr, settings_overrides}; resolve into
        # parallel lists for submission.
        common = base_settings or {
            "instrumentType": "EQUITY", "region": "USA",
            "language": "FASTEXPR", "delay": 1,
            "maxTrade": "OFF", "maxPosition": "OFF",
            "unitHandling": "VERIFY", "nanHandling": "OFF",
            "visualization": False, "testPeriod": "P0Y0M",
        }
        exprs: list[str] = []
        settings_list: list[dict] = []
        for item in expressions_raw:
            exprs.append(item["expr"])
            s = dict(common); s.update(item.get("settings", {}))
            settings_list.append(s)
    else:
        exprs = list(expressions_raw)
        settings_list = [base_settings] * len(exprs)

    log.info(f"=== batch {batch_path.name}  mech={mech}  |exprs|={len(exprs)}")

    out_path = session_dir / f"backtest_results_{batch_path.stem.replace('expressions_', '')}.json"
    results: list[dict] = []
    t0 = time.time()
    for i, (expr, s) in enumerate(zip(exprs, settings_list), 1):
        log.info(f"  [{i}/{len(exprs)}] univ={s.get('universe')} "
                 f"neut={s.get('neutralization')} decay={s.get('decay')} "
                 f"trunc={s.get('truncation')} past={s.get('pasteurization')}")
        log.info(f"      expr: {expr[:90]}")
        r = submit(cm.session, expr, s)
        results.append(asdict(r))
        if r.ok:
            log.info(f"     WQ_SH={r.sharpe:+.3f} TO={r.turnover:.3f} "
                     f"FIT={r.fitness:+.3f} ckh={r.checks_passed}/{r.checks_total} "
                     f"alpha={r.alpha_id}")
        else:
            log.info(f"     [{(r.error or '')[:150]}]")
        out_path.write_text(json.dumps(
            {"mechanism": mech,
             "settings": base_settings,
             "settings_per_expression": per_expr_settings,
             "expressions": expressions_raw,
             "results": results}, indent=2))
    log.info(f"  batch done in {(time.time()-t0)/60:.1f} min")
    return out_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", required=True,
                    help="Session folder containing batches/expressions_batch_NNNN.json")
    ap.add_argument("--target-k", type=int, default=4)
    ap.add_argument("--max-batches", type=int, default=20)
    args = ap.parse_args()

    session_dir = Path(args.session)
    batches_dir = session_dir / "batches"
    batch_files = sorted(batches_dir.glob("expressions_batch_*.json"))
    log.info(f"session={session_dir}  target_k={args.target_k}  "
             f"max_batches={args.max_batches}  found {len(batch_files)} batch file(s)")

    # Honor prior survivors before doing anything.
    prior = load_prior_results(session_dir)
    log.info(f"loaded {len(prior)} prior results from disk")
    surv = survivors(prior)
    log.info(f"prior distinct-skeleton survivors: {len(surv)}")

    cm = None
    for n, bp in enumerate(batch_files, 1):
        if n > args.max_batches:
            log.info("max_batches reached"); break
        # Skip batches whose result file already exists -- treat as done.
        result_path = session_dir / f"backtest_results_{bp.stem.replace('expressions_', '')}.json"
        if result_path.exists():
            log.info(f"skip {bp.name} (result already exists)")
            continue

        if cm is None:
            cm = authenticate()
            log.info(f"authenticated as {cm.credentials.username}")

        run_batch(session_dir, bp, cm)
        prior = load_prior_results(session_dir)
        surv = survivors(prior)
        log.info(f"  -> total survivors so far: {len(surv)}")
        for r in surv:
            log.info(f"     {r['sharpe']:+.3f} TO={r['turnover']:.3f}  "
                     f"{r['expression'][:90]}")
        if len(surv) >= args.target_k:
            log.info(f"hit target_k={args.target_k}; stopping")
            break

    # Final digest
    out_dir = session_dir / "outputs"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "survivors.json").write_text(json.dumps(
        {"count": len(surv), "target_k": args.target_k,
         "thresholds": {"sharpe": WQ_SHARPE_FLOOR, "turnover": WQ_TURNOVER_CEILING},
         "survivors": surv[:args.target_k]}, indent=2))
    log.info(f"wrote {out_dir/'survivors.json'} ({len(surv)} survivors)")

    print("\n" + "=" * 110)
    print(f"FINAL: {len(surv)}/{args.target_k} distinct-skeleton survivors "
          f"above WQ_SH > {WQ_SHARPE_FLOOR} AND TO < {WQ_TURNOVER_CEILING}")
    print()
    for r in surv[:max(args.target_k, len(surv))]:
        print(f"  WQ_SH={r['sharpe']:+.3f} TO={r['turnover']:.3f} "
              f"FIT={r['fitness']:+.3f} ckh={r['checks_passed']}/{r['checks_total']}  "
              f"{r['expression'][:90]}")
    print("=" * 110)
    return 0 if len(surv) >= args.target_k else 1


if __name__ == "__main__":
    sys.exit(main())
