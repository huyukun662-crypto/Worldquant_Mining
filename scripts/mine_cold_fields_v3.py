"""Round 3: cross the SH > 1.25 bar by porting the user's vol-skew
structure to other cold fields.

The user's baseline at SH=1.89 has structure::

    signal = ts_backfill(<cold field difference>, B)
    gate   = (ts_backfill(news_pct_90min, 5) < 1) *
             (ts_rank(abs(news_pct_30min), 60) > 0.80)
    trade_when(gate, signal, -1)

Two key ingredients:
  (a) a *cold-field difference / ratio* with a structural alpha
      (vol-skew, options-positioning skew, vol term structure, ...).
  (b) the *news-quiet-but-attentive* gate that fires on the right
      regime.

This round substitutes (a) with different cold fields while keeping
(b) (with small variations), plus a few multi-cold-field stacks.
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


CANDIDATES_V3: list[tuple[str, str, dict]] = [
    # === A. vol-skew structure with NEW cold signals ===========
    # A1. Historical volatility term structure (realized-vol skew)
    ("hv_termstructure",
     "skew = ts_backfill(historical_volatility_30 - historical_volatility_120, 5);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, skew, -1)",
     {"decay": 0, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # A2. Options-positioning skew (P/C OI term structure) with the proven news gate
    ("pcr_oi_termstructure",
     "skew = ts_backfill(pcr_oi_30 - pcr_oi_180, 5);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, skew, -1)",
     {"decay": 0, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # A3. IV call/put skew using a SHORTER tenor (the round-1 tune
    #     found the iv_tenor=60 winner; reuse the news gate here).
    ("iv_short_skew",
     "skew = ts_backfill(implied_volatility_call_30 - implied_volatility_put_30, 5);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, skew, -1)",
     {"decay": 0, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # A4. Insider sentiment difference, gated by news regime.
    ("insider_news_gated",
     "score = ts_backfill(rp_css_insider, 20) + ts_backfill(rp_ess_insider, 20);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, rank(score), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # A5. Earnings shortfall, gated by news regime.
    ("earnings_shortfall_gated",
     "sf = ts_backfill(earnings_shortfall_metric, 20);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, -rank(sf), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # === B. multi-cold-field stacks (orthogonal signal stacking) =====
    # B1. Insider sentiment + IV skew (both directional; same sign).
    ("insider_x_iv",
     "iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     "ins = ts_backfill(rp_css_insider, 20) + ts_backfill(rp_ess_insider, 20);\n"
     "score = ts_decay_linear(rank(iv) + 0.5 * rank(ins), 5);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, score, -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # B2. P/C OI skew + insider sentiment.
    ("pcr_x_insider",
     "pc = ts_backfill(pcr_oi_30 - pcr_oi_180, 10);\n"
     "ins = ts_backfill(rp_css_insider, 20);\n"
     "score = -rank(pc) + 0.3 * rank(ins);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, score, -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # B3. Dispersion penalty + insider sentiment boost.
    ("dispersion_x_insider",
     "ed = ts_backfill(fy1_eps_estimate_dispersion_2, 20);\n"
     "ins = ts_backfill(rp_css_insider, 20);\n"
     "score = -rank(ed) + 0.5 * rank(ins);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, score, -1)",
     {"decay": 6, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # === C. very tight episodic gating on the winners ==========
    # C1. Insider sentiment with 95th-percentile episodic gate
    #     (most-extreme-only) -- low turnover, high conviction.
    ("insider_tight_gate",
     "score = ts_decay_linear(\n"
     "  ts_backfill(rp_css_insider, 20) + ts_backfill(rp_ess_insider, 20), 20);\n"
     "gate = ts_rank(abs(score), 250) > 0.95;\n"
     "trade_when(gate, rank(score), -1)",
     {"decay": 12, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # C2. Short-borrow tightness with tight gate
    ("short_tight_gate",
     "supply = ts_backfill(mdl177_5shortsentimentfactor_lend_supply, 30);\n"
     "tightness = -ts_zscore(supply, 120);\n"
     "gate = ts_rank(tightness, 250) > 0.95;\n"
     "trade_when(gate, rank(tightness), -1)",
     {"decay": 12, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # C3. News-attention via news_atr_ratio with the proven news gate
    ("news_attention_gated",
     "attn = ts_backfill(news_atr_ratio, 10);\n"
     "score = ts_zscore(attn, 60);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, -rank(score), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # C4. snt1_d1 earnings sentiment combo (analyst+earnings surprise).
    ("snt1_earnings",
     "es = ts_backfill(snt1_d1_earningssurprise, 20);\n"
     "er = ts_backfill(snt1_d1_earningsrevision, 20);\n"
     "score = ts_decay_linear(rank(es) + rank(er), 10);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, score, -1)",
     {"decay": 6, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),
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
    for i, (family, expr, settings) in enumerate(CANDIDATES_V3, 1):
        log.info(f"=== v3 [{i}/{len(CANDIDATES_V3)}] family={family} ===")
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
    # Strict deliverability per CLAUDE.md
    deliverable = [r for r in all_trials
                    if r.get("ok")
                    and r["sharpe"] > 1.25
                    and r["turnover"] < 0.25
                    and sc_pass(r)]
    deliverable.sort(key=lambda r: r["sharpe"], reverse=True)

    # Fall back to top-by-SH if we have <5 strict survivors
    eligible = [r for r in all_trials
                 if r.get("ok") and r.get("turnover", 1) < 0.25 and sc_pass(r)]
    eligible.sort(key=lambda r: r["sharpe"], reverse=True)
    top5 = deliverable[:5] if len(deliverable) >= 5 else eligible[:5]

    print()
    print("=" * 130)
    print(f"All trials OK (rounds 1+2+3): {sum(1 for r in all_trials if r.get('ok'))}/{len(all_trials)}")
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
