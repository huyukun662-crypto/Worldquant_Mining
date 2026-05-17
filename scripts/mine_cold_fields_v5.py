"""Round 5: exploit the two breakthrough patterns from round 4.

Round-4 winners (SH > 1.25):
  v4.12  iv_x_short        SH=1.88  rank(iv60) + 0.5*rank(short_tightness) +
                                    news_gate, decay=4
  v4.6   insider_x_iv90    SH=1.33  rank(iv90) + rank(insider) + news_gate

Goal: get 3 more SH>1.25 alphas to round out a deliverable 5.
"""

from __future__ import annotations
import json
import sys
from pathlib import Path
from dataclasses import asdict

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mine_cold_fields import (  # noqa: E402
    CandidateResult, submit, fetch_self_corr, FIXED_SETTINGS, _load,
    VENDOR, REPO, log,
)


NEWS_GATE = ("gate = (ts_backfill(news_pct_90min, 5) < 1) * "
             "(ts_rank(abs(news_pct_30min), 60) > 0.80);")


CANDIDATES_V5: list[tuple[str, str, dict]] = [
    # === Variants of iv_x_short (v4.12 winner, SH=1.88) =================
    # P1. IV tenor 30 instead of 60.
    ("iv30_x_short",
     "iv = ts_backfill(implied_volatility_call_30 - implied_volatility_put_30, 5);\n"
     "supply = ts_backfill(mdl177_5shortsentimentfactor_lend_supply, 30);\n"
     "tightness = -ts_zscore(supply, 120);\n"
     "score = rank(iv) + 0.5 * rank(tightness);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(score, 5), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # P2. IV tenor 90.
    ("iv90_x_short",
     "iv = ts_backfill(implied_volatility_call_90 - implied_volatility_put_90, 5);\n"
     "supply = ts_backfill(mdl177_5shortsentimentfactor_lend_supply, 30);\n"
     "tightness = -ts_zscore(supply, 120);\n"
     "score = rank(iv) + 0.5 * rank(tightness);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(score, 5), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # P3. IV tenor 120, heavier short weight.
    ("iv120_x_short_heavy",
     "iv = ts_backfill(implied_volatility_call_120 - implied_volatility_put_120, 5);\n"
     "supply = ts_backfill(mdl177_5shortsentimentfactor_lend_supply, 30);\n"
     "tightness = -ts_zscore(supply, 120);\n"
     "score = rank(iv) + 1.0 * rank(tightness);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(score, 5), -1)",
     {"decay": 6, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # P4. iv60 + short (winner) but with INDUSTRY neut.
    ("iv60_x_short_industry",
     "iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     "supply = ts_backfill(mdl177_5shortsentimentfactor_lend_supply, 30);\n"
     "tightness = -ts_zscore(supply, 120);\n"
     "score = rank(iv) + 0.5 * rank(tightness);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(score, 5), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "INDUSTRY"}),

    # P5. iv60 + short BUT no news gate (raw episodic on attention).
    ("iv60_x_short_no_gate",
     "iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     "supply = ts_backfill(mdl177_5shortsentimentfactor_lend_supply, 30);\n"
     "tightness = -ts_zscore(supply, 120);\n"
     "score = rank(iv) + 0.5 * rank(tightness);\n"
     "ts_decay_linear(score, 5)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # === Variants of insider_x_iv90 (v4.6 winner, SH=1.33) ==============
    # Q1. IV60 + insider (mix the iv_x_short ingredient).
    ("insider_x_iv60",
     "iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     "ins = ts_backfill(rp_css_insider, 30) + ts_backfill(rp_ess_insider, 30);\n"
     "score = ts_decay_linear(rank(iv) + rank(ins), 10);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, score, -1)",
     {"decay": 6, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # Q2. insider × IV120
    ("insider_x_iv120",
     "iv = ts_backfill(implied_volatility_call_120 - implied_volatility_put_120, 5);\n"
     "ins = ts_backfill(rp_css_insider, 30) + ts_backfill(rp_ess_insider, 30);\n"
     "score = ts_decay_linear(rank(iv) + rank(ins), 10);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, score, -1)",
     {"decay": 6, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # Q3. insider × IV90 with heavier insider weight.
    ("insider2x_x_iv90",
     "iv = ts_backfill(implied_volatility_call_90 - implied_volatility_put_90, 5);\n"
     "ins = ts_backfill(rp_css_insider, 30) + ts_backfill(rp_ess_insider, 30);\n"
     "score = ts_decay_linear(rank(iv) + 2.0 * rank(ins), 10);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, score, -1)",
     {"decay": 6, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # === Triple stacks =================================================
    # R1. iv60 + short + insider (3-way, the v4.7 stack but with insider
    #     weight reduced to 0.3 — v4.7 was 1.25 exactly).
    ("iv_short_insider_lite",
     "iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     "ins = ts_backfill(rp_css_insider, 30);\n"
     "supply = ts_backfill(mdl177_5shortsentimentfactor_lend_supply, 30);\n"
     "tightness = -ts_zscore(supply, 120);\n"
     "score = rank(iv) + 0.5*rank(tightness) + 0.3*rank(ins);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(score, 5), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # R2. iv60 + short + dispersion (uncertainty premium).
    ("iv_short_disp",
     "iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     "ed = ts_backfill(fy1_eps_estimate_dispersion_2, 30);\n"
     "supply = ts_backfill(mdl177_5shortsentimentfactor_lend_supply, 30);\n"
     "tightness = -ts_zscore(supply, 120);\n"
     "score = rank(iv) + 0.5*rank(tightness) - 0.3*rank(ed);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(score, 5), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # R3. iv60 + short with longer zscore window on short (240).
    ("iv60_x_short_long_z",
     "iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     "supply = ts_backfill(mdl177_5shortsentimentfactor_lend_supply, 30);\n"
     "tightness = -ts_zscore(supply, 240);\n"
     "score = rank(iv) + 0.5 * rank(tightness);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(score, 5), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # R4. iv60 + short with DECAY=8 (smoother score persistence)
    ("iv60_x_short_decay8",
     "iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     "supply = ts_backfill(mdl177_5shortsentimentfactor_lend_supply, 30);\n"
     "tightness = -ts_zscore(supply, 120);\n"
     "score = rank(iv) + 0.5 * rank(tightness);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(score, 5), -1)",
     {"decay": 8, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),
]


def main():
    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")

    out_path = REPO / "WQ_COLD_FACTORS.json"
    prior = []
    if out_path.exists():
        old = json.load(open(out_path))
        prior = old.get("all_trials") or (old if isinstance(old, list) else [])
        log.info(f"loaded {len(prior)} prior trials")

    results: list[CandidateResult] = []
    for i, (family, expr, settings) in enumerate(CANDIDATES_V5, 1):
        log.info(f"=== v5 [{i}/{len(CANDIDATES_V5)}] family={family} ===")
        log.info(f"   expr: {expr.replace(chr(10), ' | ')}")
        res = submit(cm.session, family, expr, settings)
        results.append(res)
        if not res.ok:
            log.warning(f"   FAILED: {res.error[:160]}")
        else:
            log.info(f"   SH={res.sharpe:+.3f} TO={res.turnover:.3f} "
                      f"FIT={res.fitness:+.3f} checks={res.checks_passed}/{res.checks_total} "
                      f"alpha={res.alpha_id}")
        all_trials = prior + [asdict(r) for r in results]
        with open(out_path, "w") as f:
            json.dump({"all_trials": all_trials}, f, indent=2)

    log.info("=== pass 2: self-correlation ===")
    for r in results:
        if not r.ok or not r.alpha_id: continue
        sc, top, st = fetch_self_corr(cm.session, r.alpha_id, timeout_s=90)
        r.self_corr = sc
        if top:
            r.self_corr_peer = top.get("id")
            r.self_corr_peer_sharpe = top.get("sharpe")
        sc_s = f"{sc:.3f}" if sc is not None else "?"
        peer = f"{top['id']}@SH{top['sharpe']}" if top else "(none)"
        log.info(f"   {r.alpha_id} self_corr={sc_s} ({st}) peer={peer}")

    def sc_pass(r):
        if r.get("self_corr") is None: return False
        if abs(r["self_corr"]) < 0.70: return True
        peer_sh = r.get("self_corr_peer_sharpe")
        return (isinstance(peer_sh, (int, float))
                and r["sharpe"] >= 1.10 * peer_sh)

    all_trials = prior + [asdict(r) for r in results]
    deliverable = [r for r in all_trials
                    if r.get("ok") and r["sharpe"] > 1.25
                    and r["turnover"] < 0.25 and sc_pass(r)]
    deliverable.sort(key=lambda r: r["sharpe"], reverse=True)
    eligible = [r for r in all_trials
                 if r.get("ok") and r.get("turnover", 1) < 0.25 and sc_pass(r)]
    eligible.sort(key=lambda r: r["sharpe"], reverse=True)
    top5 = deliverable[:5] if len(deliverable) >= 5 else eligible[:5]

    print()
    print("=" * 130)
    print(f"All trials OK (rounds 1..5): {sum(1 for r in all_trials if r.get('ok'))}/{len(all_trials)}")
    print(f"Strictly deliverable (SH>1.25 AND TO<0.25 AND sc OK): {len(deliverable)}")
    print(f"{'#':<3}{'family':<28}{'SH':>7}{'TO':>7}{'FIT':>7}{'chk':>6}{'sc':>7} "
           "alpha_id   expr_brief")
    for i, r in enumerate(eligible[:20], 1):
        marker = "★" if r in deliverable else " "
        first_line = r["expression"].split("\n")[-1][:60]
        sc = f"{r['self_corr']:+.3f}" if r.get("self_corr") is not None else "  -  "
        print(f"{marker}{i:<2}{r['family']:<28}{r['sharpe']:7.3f}{r['turnover']:7.3f}"
               f"{r['fitness']:7.3f} {r['checks_passed']:>2}/{r['checks_total']:<2}"
               f"{sc:>7} {r['alpha_id']:<10} {first_line}")
    print("=" * 130)

    delivery = {
        "selected": [
            {
                "rank": i + 1,
                "family": r["family"],
                "alpha_id": r["alpha_id"],
                "sharpe": r["sharpe"],
                "turnover": r["turnover"],
                "fitness": r["fitness"],
                "returns": r["returns"],
                "drawdown": r["drawdown"],
                "checks_passed": r["checks_passed"],
                "checks_total": r["checks_total"],
                "self_corr": r["self_corr"],
                "self_corr_peer": r.get("self_corr_peer"),
                "self_corr_peer_sharpe": r.get("self_corr_peer_sharpe"),
                "expression": r["expression"],
                "settings": {k: r["settings"][k] for k in
                             ("universe", "delay", "decay", "truncation",
                              "neutralization", "pasteurization")},
                "meets_strict_bar": (r["sharpe"] > 1.25 and r["turnover"] < 0.25
                                       and sc_pass(r)),
            }
            for i, r in enumerate(top5)
        ],
        "delivery_summary": {
            "total_trials": len(all_trials),
            "ok_trials": sum(1 for r in all_trials if r.get("ok")),
            "strict_deliverable_count": len(deliverable),
            "rule": "SH>1.25 AND TO<0.25 AND (max|self_corr|<0.7 OR SH>=1.10*peer_SH)",
        },
        "all_trials": all_trials,
    }
    with open(out_path, "w") as f:
        json.dump(delivery, f, indent=2)
    log.info(f"wrote {out_path}: {len(top5)} factors "
              f"({len(deliverable)} meet strict bar)")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
