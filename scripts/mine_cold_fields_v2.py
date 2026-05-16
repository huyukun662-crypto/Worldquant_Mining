"""Round 2 of cold-field mining: trade_when episodic gating + refined signals.

Round 1 (mine_cold_fields.py) found that raw cross-sectional z/rank
combinations of cold fields max out around SH=0.96 on this account
(insider_news css+ess). The winning pattern in the user's existing
volatility-skew alpha (SH=1.89) was the trade_when(episodic_gate,
signal, -1) wrapper — fire only on extreme readings.

This round applies that wrapper to 10 cold-field signals. Output
merges with round 1 into WQ_COLD_FACTORS.json (top 5 by Sharpe).
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

CANDIDATES_V2: list[tuple[str, str, dict]] = [
    # === insider_news refinements (round-1 leader) ============
    # Gate on high news-influence-percentile, then take CSS direction.
    ("insider_news",
     "nip = ts_backfill(rp_nip_insider, 20);\n"
     "css = ts_backfill(rp_css_insider, 20);\n"
     "gate = ts_rank(nip, 60) > 0.90;\n"
     "trade_when(gate, rank(ts_decay_linear(css, 10)), -1)",
     {"decay": 8, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # Episodic css + ess together; longer rank window.
    ("insider_news",
     "css = ts_backfill(rp_css_insider, 30);\n"
     "ess = ts_backfill(rp_ess_insider, 30);\n"
     "score = ts_decay_linear(css + ess, 20);\n"
     "gate = ts_rank(abs(score), 120) > 0.85;\n"
     "trade_when(gate, rank(score), -1)",
     {"decay": 12, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # === pcr_oi refinements ====================================
    # Episodic option-positioning shift, contrarian.
    ("pcr_oi",
     "shift = ts_backfill(pcr_oi_30, 5) - ts_backfill(pcr_oi_90, 20);\n"
     "gate = ts_rank(abs(shift), 60) > 0.90;\n"
     "trade_when(gate, -rank(ts_decay_linear(shift, 5)), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # Cross-tenor curve (very short vs very long); zscore time-series.
    ("pcr_oi",
     "curve = ts_backfill(pcr_oi_20, 10) - ts_backfill(pcr_oi_360, 30);\n"
     "z = ts_zscore(curve, 60);\n"
     "gate = abs(z) > 1.5;\n"
     "trade_when(gate, -rank(z), -1)",
     {"decay": 8, "truncation": 0.02, "neutralization": "INDUSTRY"}),

    # === short_sent refinements ===============================
    # Spike in days-to-cover (short squeeze setup) -> long the squeezed.
    ("short_sent",
     "dtc = ts_backfill(mdl177_5shortsentimentfactor_days_to_cover, 20);\n"
     "spike = ts_zscore(dtc, 60);\n"
     "gate = spike > 1.5;\n"
     "trade_when(gate, -rank(spike), -1)",
     {"decay": 6, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # Borrow-supply tightness (low supply -> hard to short -> upward).
    ("short_sent",
     "supply = ts_backfill(mdl177_5shortsentimentfactor_lend_supply, 20);\n"
     "tightness = -ts_zscore(supply, 60);\n"
     "gate = ts_rank(tightness, 60) > 0.85;\n"
     "trade_when(gate, rank(tightness), -1)",
     {"decay": 8, "truncation": 0.02, "neutralization": "INDUSTRY"}),

    # === social media refinements =============================
    # Buzz-spike + sentiment direction (attention-driven momentum).
    ("social",
     "buzz = ts_backfill(snt_buzz_fast_d1, 10);\n"
     "sent = ts_backfill(snt_value_fast_d1, 10);\n"
     "spike = ts_zscore(buzz, 60);\n"
     "gate = spike > 1.5;\n"
     "trade_when(gate, rank(ts_decay_linear(sent, 5)), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # === dispersion refinements ==============================
    # High dispersion + rising -> uncertainty premium (short).
    ("dispersion",
     "ed = ts_backfill(fy1_eps_estimate_dispersion_2, 20);\n"
     "rising = ts_delta(ed, 5);\n"
     "gate = (ts_rank(ed, 60) > 0.80) * (rising > 0);\n"
     "trade_when(gate, -rank(ed), -1)",
     {"decay": 12, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # === NEW family: news-attention via news_atr_ratio ========
    # Day's news-driven move vs typical move; large ratio -> follow.
    ("news_atr",
     "atr = ts_backfill(news_atr_ratio, 5);\n"
     "score = ts_zscore(atr, 60);\n"
     "gate = score > 1.5;\n"
     "trade_when(gate, rank(ts_decay_linear(atr, 5)), -1)",
     {"decay": 6, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),

    # === NEW family: earnings_shortfall_metric ===============
    # Recent earnings shortfall events; short the shortfallers.
    ("earnings_shortfall",
     "sf = ts_backfill(earnings_shortfall_metric, 30);\n"
     "gate = ts_rank(abs(sf), 90) > 0.85;\n"
     "trade_when(gate, -rank(ts_decay_linear(sf, 10)), -1)",
     {"decay": 8, "truncation": 0.02, "neutralization": "SUBINDUSTRY"}),
]


def main():
    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")

    # Load round-1 results to merge with.
    out_path = REPO / "WQ_COLD_FACTORS.json"
    round1: list[dict] = []
    if out_path.exists():
        old = json.load(open(out_path))
        round1 = old.get("all_trials") or old if isinstance(old, list) else \
                 old.get("all_trials") or []
        log.info(f"loaded {len(round1)} round-1 trials")

    results: list[CandidateResult] = []
    for i, (family, expr, settings) in enumerate(CANDIDATES_V2, 1):
        log.info(f"=== v2 [{i}/{len(CANDIDATES_V2)}] family={family} ===")
        log.info(f"   expr: {expr.replace(chr(10), ' | ')}")
        res = submit(cm.session, family, expr, settings)
        results.append(res)
        if not res.ok:
            log.warning(f"   FAILED: {res.error[:160]}")
        else:
            log.info(f"   SH={res.sharpe:+.3f} TO={res.turnover:.3f} "
                      f"FIT={res.fitness:+.3f} checks={res.checks_passed}/{res.checks_total} "
                      f"alpha={res.alpha_id}")
        # Persist combined progress.
        all_trials = round1 + [asdict(r) for r in results]
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

    # Merge and re-rank
    def sc_pass(r):
        if r.get("self_corr") is None: return False
        if abs(r["self_corr"]) < 0.70: return True
        peer_sh = r.get("self_corr_peer_sharpe")
        return (isinstance(peer_sh, (int, float))
                and r["sharpe"] >= 1.10 * peer_sh)

    all_trials = round1 + [asdict(r) for r in results]
    eligible = [r for r in all_trials
                 if r.get("ok") and r.get("turnover", 1) < 0.25 and sc_pass(r)]
    eligible.sort(key=lambda r: r["sharpe"], reverse=True)
    top5 = eligible[:5]

    print()
    print("=" * 120)
    print(f"All trials OK (rounds 1+2): {sum(1 for r in all_trials if r.get('ok'))}/{len(all_trials)}")
    print(f"Eligible (TO<0.25 AND self_corr passes): {len(eligible)}")
    print(f"{'#':<3}{'family':<18}{'SH':>7}{'TO':>7}{'FIT':>7}{'chk':>6}{'sc':>7} "
           "alpha_id   expr_brief")
    for i, r in enumerate(eligible[:15], 1):
        marker = "★" if i <= 5 else " "
        first_line = r["expression"].split("\n")[-1][:60]
        sc = f"{r['self_corr']:+.3f}" if r.get("self_corr") is not None else "  -  "
        print(f"{marker}{i:<2}{r['family']:<18}{r['sharpe']:7.3f}{r['turnover']:7.3f}"
               f"{r['fitness']:7.3f} {r['checks_passed']:>2}/{r['checks_total']:<2}"
               f"{sc:>7} {r['alpha_id']:<10} {first_line}")
    print("=" * 120)

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
            }
            for i, r in enumerate(top5)
        ],
        "all_trials": all_trials,
    }
    with open(out_path, "w") as f:
        json.dump(delivery, f, indent=2)
    log.info(f"wrote {out_path}: {len(top5)} delivered factors")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
