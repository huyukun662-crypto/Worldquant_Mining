"""Round 4: push leaders over SH > 1.25.

Top of rounds 1+2+3:
  v3.10  short_tight_gate     SH=1.19  trade_when(gate>0.95, rank(tightness), -1)
  v3.4   insider_news_gated   SH=1.04  trade_when(news_gate, rank(css+ess), -1)
  v3.6   insider_x_iv         SH=1.03  trade_when(news_gate, rank(iv)+0.5*rank(ins), -1)

This round explores variants of these three families plus a few
orthogonal stacks.  Goal: produce >=5 alphas with SH>1.25.
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


CANDIDATES_V4: list[tuple[str, str, dict]] = [
    # === SHORT_TIGHT_GATE variants (current leader SH=1.19) =========
    # T1. Same as v3.10 but with the proven news gate INSTEAD of the
    #     tight-percentile gate.
    ("short_news_gated",
     "supply = ts_backfill(mdl177_5shortsentimentfactor_lend_supply, 30);\n"
     "tightness = -ts_zscore(supply, 120);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, rank(tightness), -1)",
     {"decay": 12, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # T2. dmd_supply instead of lend_supply (demand minus supply).
    ("short_dmd_supply",
     "ds = ts_backfill(mdl177_5shortsentimentfactor_dmd_supply, 30);\n"
     "score = ts_zscore(ds, 120);\n"
     "gate = ts_rank(score, 250) > 0.95;\n"
     "trade_when(gate, -rank(score), -1)",
     {"decay": 12, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # T3. utilization with tight gate.
    ("short_util",
     "u = ts_backfill(mdl177_5shortsentimentfactor_act_util, 30);\n"
     "score = ts_zscore(u, 120);\n"
     "gate = ts_rank(score, 250) > 0.95;\n"
     "trade_when(gate, -rank(score), -1)",
     {"decay": 12, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # T4. Same as v3.10 winner but with SECTOR neut (try wider grouping).
    ("short_tight_sector",
     "supply = ts_backfill(mdl177_5shortsentimentfactor_lend_supply, 30);\n"
     "tightness = -ts_zscore(supply, 120);\n"
     "gate = ts_rank(tightness, 250) > 0.95;\n"
     "trade_when(gate, rank(tightness), -1)",
     {"decay": 12, "truncation": 0.02, "neutralization": "SECTOR"}),

    # T5. Same as v3.10 winner but on TOP1000 (smaller more-liquid set).
    ("short_tight_top1000",
     "supply = ts_backfill(mdl177_5shortsentimentfactor_lend_supply, 30);\n"
     "tightness = -ts_zscore(supply, 120);\n"
     "gate = ts_rank(tightness, 250) > 0.95;\n"
     "trade_when(gate, rank(tightness), -1)",
     {"universe": "TOP1000", "decay": 12, "truncation": 0.02,
      "neutralization": "SUBINDUSTRY"}),

    # === INSIDER_X_IV stack variants (current SH=1.03) ===========
    # S1. Heavier insider weight + IV 90.
    ("insider_x_iv90",
     "iv = ts_backfill(implied_volatility_call_90 - implied_volatility_put_90, 5);\n"
     "ins = ts_backfill(rp_css_insider, 30) + ts_backfill(rp_ess_insider, 30);\n"
     "score = ts_decay_linear(rank(iv) + rank(ins), 10);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, score, -1)",
     {"decay": 6, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # S2. Insider + IV + short tightness (3-way stack).
    ("insider_iv_short_stack",
     "iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     "ins = ts_backfill(rp_css_insider, 20) + ts_backfill(rp_ess_insider, 20);\n"
     "supply = ts_backfill(mdl177_5shortsentimentfactor_lend_supply, 30);\n"
     "tightness = -ts_zscore(supply, 120);\n"
     "score = ts_decay_linear(rank(iv) + 0.5*rank(ins) + 0.5*rank(tightness), 5);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, score, -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # === INSIDER_NEWS_GATED variants (current SH=1.04) ============
    # I1. Add nip as a positive weighting (informed-news influence).
    ("insider_news_full",
     "css = ts_backfill(rp_css_insider, 30);\n"
     "ess = ts_backfill(rp_ess_insider, 30);\n"
     "nip = ts_backfill(rp_nip_insider, 30);\n"
     "score = ts_decay_linear(rank(css) + rank(ess) + 0.3 * rank(nip), 10);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, score, -1)",
     {"decay": 6, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # I2. Insider + dispersion penalty (high dispersion -> demote).
    ("insider_minus_dispersion",
     "ins = ts_backfill(rp_css_insider, 30) + ts_backfill(rp_ess_insider, 30);\n"
     "ed = ts_backfill(fy1_eps_estimate_dispersion_2, 30);\n"
     "score = rank(ins) - 0.5 * rank(ed);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(score, 10), -1)",
     {"decay": 8, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # I3. Same as v3.4 winner but with tighter news gate
    #     (need *both* very rare conditions to fire).
    ("insider_double_gate",
     "score = ts_backfill(rp_css_insider, 20) + ts_backfill(rp_ess_insider, 20);\n"
     "gate1 = (ts_backfill(news_pct_90min, 5) < 1);\n"
     "gate2 = ts_rank(abs(news_pct_30min), 60) > 0.90;\n"
     "gate3 = ts_rank(abs(score), 120) > 0.80;\n"
     "trade_when(gate1 * gate2 * gate3, rank(score), -1)",
     {"decay": 6, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # === Other stacks ====================================
    # X1. Use the news_attention_gated structure (news_atr_ratio is cold
    #     news data) but DIRECTLY mix with insider, NOT separately gate.
    ("attn_x_insider",
     "attn = ts_zscore(ts_backfill(news_atr_ratio, 10), 60);\n"
     "ins = ts_backfill(rp_css_insider, 20) + ts_backfill(rp_ess_insider, 20);\n"
     "score = ts_decay_linear(rank(ins) + 0.3 * rank(attn), 10);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, score, -1)",
     {"decay": 6, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # X2. IV-skew + short tightness (no insider; just options + borrow).
    ("iv_x_short",
     "iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     "supply = ts_backfill(mdl177_5shortsentimentfactor_lend_supply, 30);\n"
     "tightness = -ts_zscore(supply, 120);\n"
     "score = rank(iv) + 0.5 * rank(tightness);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(score, 5), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),
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
    for i, (family, expr, settings) in enumerate(CANDIDATES_V4, 1):
        log.info(f"=== v4 [{i}/{len(CANDIDATES_V4)}] family={family} ===")
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
    print(f"All trials OK (rounds 1..4): {sum(1 for r in all_trials if r.get('ok'))}/{len(all_trials)}")
    print(f"Strictly deliverable (SH>1.25 AND TO<0.25 AND sc OK): {len(deliverable)}")
    print(f"{'#':<3}{'family':<26}{'SH':>7}{'TO':>7}{'FIT':>7}{'chk':>6}{'sc':>7} "
           "alpha_id   expr_brief")
    for i, r in enumerate(eligible[:20], 1):
        marker = "★" if r in deliverable else " "
        first_line = r["expression"].split("\n")[-1][:60]
        sc = f"{r['self_corr']:+.3f}" if r.get("self_corr") is not None else "  -  "
        print(f"{marker}{i:<2}{r['family']:<26}{r['sharpe']:7.3f}{r['turnover']:7.3f}"
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
