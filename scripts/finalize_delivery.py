"""Pick a structure-diverse top-5 from the full WQ_COLD_FACTORS.json
ledger (66 successful trials across 7 rounds) and write the final
delivery payload.

Diversification rules:
  * cap each "family" at 2 picks
  * always include the highest-Sharpe member of each unique family
    that has SH>1.25 + TO<0.25 + self-corr passes
  * pick by Sharpe within those caps
"""

from __future__ import annotations
import json
from pathlib import Path
from collections import defaultdict

REPO = Path(__file__).resolve().parent.parent
PATH = REPO / "WQ_COLD_FACTORS.json"


def sc_pass(r):
    sc = r.get("self_corr")
    if sc is None: return False
    if abs(sc) < 0.70: return True
    peer_sh = r.get("self_corr_peer_sharpe")
    return (isinstance(peer_sh, (int, float))
            and r["sharpe"] >= 1.10 * peer_sh)


def family_key(family: str) -> str:
    """Collapse v3/v4/v5/v6 variants of similar mining families into
    structural buckets so we can diversify properly."""
    # All iv_*_short_* variants share the rank(iv)+w*rank(short_borrow)
    # rank-sum structure with the news_pct gate.
    if family.startswith("iv") and "short" in family:        return "iv_x_short_ranksum"
    if family in ("iv_x_short", "iv_x_short_ranksum"):       return "iv_x_short_ranksum"
    if family.startswith("insider_x_iv"):                    return "insider_x_iv_ranksum"
    if family == "iv_short_insider_lite":                    return "iv_short_insider_3way"
    if family.startswith("g9"):                              return "scale_winsorize"
    if family.startswith("g"):                               return f"round7_{family}"
    return family


def main():
    data = json.load(open(PATH))
    trials = data.get("all_trials", data) if isinstance(data, dict) else data
    print(f"loaded {len(trials)} trials")

    eligible = [r for r in trials
                 if r.get("ok") and r["sharpe"] > 1.25
                 and r["turnover"] < 0.25 and sc_pass(r)]
    eligible.sort(key=lambda r: r["sharpe"], reverse=True)
    print(f"{len(eligible)} strict-deliverable (SH>1.25, TO<0.25, sc OK)")

    # Diversified pick: at most 2 per family bucket, prefer high SH.
    by_bucket: dict[str, list[dict]] = defaultdict(list)
    for r in eligible:
        by_bucket[family_key(r["family"])].append(r)

    picks = []
    cap = 2
    while len(picks) < 5 and by_bucket:
        # Take the highest SH still available across all buckets that
        # have not yet hit cap.
        candidates = []
        for bucket, lst in by_bucket.items():
            n_already = sum(1 for p in picks if family_key(p["family"]) == bucket)
            if n_already >= cap: continue
            if lst:
                candidates.append((lst[0]["sharpe"], bucket, lst[0]))
        if not candidates: break
        candidates.sort(reverse=True)
        _, bucket, pick = candidates[0]
        picks.append(pick)
        by_bucket[bucket].pop(0)

    print()
    print("=" * 110)
    print("FINAL DIVERSIFIED TOP 5")
    print(f"{'#':<3}{'bucket':<26}{'family':<24}{'SH':>7}{'TO':>7}{'FIT':>7}{'chk':>6}{'sc':>7} alpha_id")
    for i, p in enumerate(picks, 1):
        sc = f"{p['self_corr']:+.3f}" if p.get("self_corr") is not None else "  -  "
        print(f"{i:<3}{family_key(p['family']):<26}{p['family']:<24}{p['sharpe']:7.3f}"
               f"{p['turnover']:7.3f}{p['fitness']:7.3f} "
               f"{p['checks_passed']:>2}/{p['checks_total']:<2}{sc:>7} {p['alpha_id']:<10}")
    print("=" * 110)

    delivery = {
        "selected": [
            {
                "rank": i + 1,
                "family": p["family"],
                "structure_bucket": family_key(p["family"]),
                "alpha_id": p["alpha_id"],
                "sharpe": p["sharpe"],
                "turnover": p["turnover"],
                "fitness": p["fitness"],
                "returns": p["returns"],
                "drawdown": p["drawdown"],
                "margin": p.get("margin"),
                "checks_passed": p["checks_passed"],
                "checks_total": p["checks_total"],
                "self_corr": p["self_corr"],
                "self_corr_peer": p.get("self_corr_peer"),
                "self_corr_peer_sharpe": p.get("self_corr_peer_sharpe"),
                "expression": p["expression"],
                "settings": {k: p["settings"][k] for k in
                             ("universe", "delay", "decay", "truncation",
                              "neutralization", "pasteurization")},
            }
            for i, p in enumerate(picks)
        ],
        "delivery_summary": {
            "total_trials": len(trials),
            "ok_trials": sum(1 for r in trials if r.get("ok")),
            "strict_deliverable_count": len(eligible),
            "rule": "SH>1.25 AND TO<0.25 AND (max|self_corr|<0.7 OR SH>=1.10*peer_SH)",
            "diversification_rule": "at most 2 alphas per structural bucket "
                                    "(iv_x_short_ranksum, insider_x_iv_ranksum, "
                                    "scale_winsorize, ...)",
        },
        "all_trials": trials,
    }
    with open(PATH, "w") as f:
        json.dump(delivery, f, indent=2)
    print(f"wrote {PATH}: {len(picks)} delivered factors")
    return 0


if __name__ == "__main__":
    raise SystemExit(main() or 0)
