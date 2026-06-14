"""Low-correlation alpha selector (WorldQuant Brain PnL-based).

Given one or more JSON files of completed alphas (each item must have an
`alpha_id`), this fetches each alpha's daily PnL from WQ Brain
(`/alphas/{id}/recordsets/pnl`), computes the pairwise Pearson correlation
of daily PnL *increments* over the shared date range, and greedily selects a
maximally low-correlation subset.

Use it to pick a basket of submittable factors that are mutually orthogonal
(and orthogonal to an already-submitted reference set), which keeps WQ Brain's
SELF_CORRELATION check happy at submit time.

Usage:
    # rank+filter v3 survivors, keeping each only if |corr| < 0.5 to every
    # already-kept alpha AND every alpha in the reference set:
    python scripts/lowcorr_select.py \
        --candidates WQ_SUBMITTABLE_CANDIDATES.json \
        --reference  WQ_SUBMITTABLE_CANDIDATES_v1.json \
        --threshold 0.5 \
        --out WQ_LOWCORR_CANDIDATES.json
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import time
from pathlib import Path

import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("lowcorr")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"


def _load(p: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fetch_pnl(session, alpha_id: str, tries: int = 12) -> dict[str, float] | None:
    """Return {date: daily_pnl_increment} for an alpha, or None on failure.

    The recordset is cumulative PnL; we diff it into daily increments.
    """
    url = f"https://api.worldquantbrain.com/alphas/{alpha_id}/recordsets/pnl"
    for i in range(tries):
        try:
            r = session.get(url, timeout=30)
        except Exception as e:  # transient network
            log.info(f"   {alpha_id}: net {type(e).__name__}; retry"); time.sleep(5); continue
        if r.status_code == 429:
            time.sleep(float(r.headers.get("Retry-After") or 15)); continue
        if r.status_code == 200 and r.text.strip():
            recs = r.json().get("records") or []
            if not recs:
                return None
            # records are [date, cumulative_pnl]; diff to daily increments
            dates = [row[0] for row in recs]
            cum = np.array([float(row[1]) for row in recs], dtype=float)
            inc = np.diff(cum, prepend=cum[0])
            return dict(zip(dates, inc.tolist()))
        # 200-but-empty means "still computing" -> wait and retry
        time.sleep(float(r.headers.get("Retry-After") or 4))
    log.warning(f"   {alpha_id}: PnL not available after {tries} tries")
    return None


def corr(a: dict[str, float], b: dict[str, float]) -> float:
    """Pearson correlation of two date->increment maps over shared dates."""
    common = sorted(set(a) & set(b))
    if len(common) < 60:
        return 0.0
    x = np.array([a[d] for d in common]); y = np.array([b[d] for d in common])
    if x.std() < 1e-12 or y.std() < 1e-12:
        return 0.0
    return float(np.corrcoef(x, y)[0, 1])


def uniq_by_alpha(items: list[dict]) -> list[dict]:
    seen = {}
    for it in items:
        aid = it.get("alpha_id")
        if aid and aid not in seen:
            seen[aid] = it
    return list(seen.values())


def desirability(it: dict) -> float:
    return (it.get("fitness", 0) + 0.3 * it.get("sharpe", 0)
            - 2.0 * it.get("drawdown", 0) - 2.0 * it.get("turnover", 0))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidates", required=True,
                    help="JSON of candidate alphas to filter (need alpha_id)")
    ap.add_argument("--reference", default=None,
                    help="JSON of already-kept/submitted alphas to stay "
                         "orthogonal to (e.g. the leverage family)")
    ap.add_argument("--threshold", type=float, default=0.5,
                    help="max |corr| allowed vs any kept/reference alpha")
    ap.add_argument("--out", default="WQ_LOWCORR_CANDIDATES.json")
    args = ap.parse_args()

    cands = uniq_by_alpha(json.load(open(args.candidates)))
    cands = [c for c in cands if c.get("alpha_id")]
    cands.sort(key=desirability, reverse=True)
    refs = []
    if args.reference and Path(args.reference).exists():
        refs = [r for r in uniq_by_alpha(json.load(open(args.reference)))
                if r.get("alpha_id")]
    log.info(f"{len(cands)} unique candidates, {len(refs)} reference alphas, "
             f"threshold |corr|<{args.threshold}")

    cm = _load(VENDOR / "core" / "credential_manager.py", "cm").CredentialManager(
        base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("auth failed"); return 2
    s = cm.session

    # Fetch PnL for references + candidates
    pnl: dict[str, dict] = {}
    for r in refs + cands:
        aid = r["alpha_id"]
        if aid in pnl:
            continue
        p = fetch_pnl(s, aid)
        if p:
            pnl[aid] = p
            log.info(f"   PnL {aid}: {len(p)} days")
        time.sleep(0.5)

    # Greedy selection: keep a candidate iff its max |corr| to all already
    # kept + all references is below the threshold.
    kept: list[dict] = []
    kept_ids = [r["alpha_id"] for r in refs if r["alpha_id"] in pnl]
    rows = []
    for c in cands:
        aid = c["alpha_id"]
        if aid not in pnl:
            continue
        cmax, cwith = 0.0, ""
        for kid in kept_ids:
            cval = abs(corr(pnl[aid], pnl[kid]))
            if cval > cmax:
                cmax, cwith = cval, kid
        decision = cmax < args.threshold
        c = dict(c)
        c["max_abs_corr"] = round(cmax, 3)
        c["max_corr_with"] = cwith
        c["kept"] = decision
        rows.append(c)
        if decision:
            kept.append(c); kept_ids.append(aid)
        log.info(f"   {aid} SH={c.get('sharpe'):.2f} TO={c.get('turnover'):.3f} "
                 f"max|corr|={cmax:.2f} (vs {cwith or '-'}) -> "
                 f"{'KEEP' if decision else 'drop'}")

    json.dump(kept, open(args.out, "w"), indent=2)
    json.dump(rows, open(args.out.replace(".json", "_all.json"), "w"), indent=2)

    print("\n" + "=" * 100)
    print(f"selected {len(kept)} mutually-low-correlation alphas "
          f"(|corr| < {args.threshold} vs each other"
          f"{' and the reference set' if refs else ''}):\n")
    print(f"{'SH':>5}{'TO':>7}{'FIT':>6}{'DD':>7}  {'alpha_id':<10}{'maxcorr':>8}  expression")
    for c in kept:
        print(f"{c.get('sharpe',0):5.2f}{c.get('turnover',0):7.3f}{c.get('fitness',0):6.2f}"
              f"{c.get('drawdown',0):7.3f}  {c['alpha_id']:<10}{c['max_abs_corr']:8.2f}  "
              f"{c.get('optimized', c.get('expression',''))[:54]}")
    print("=" * 100)
    log.info(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
