"""Round 6: rank/sign robustness check on the final 5 delivered alphas.

Per the WQ Brain training cheatsheet, a robust alpha should preserve
its Sharpe when its signal is wrapped in rank()/sign() — magnitude
erasure variants.  If SH collapses, the alpha leans on magnitude
noise (fragile).

The 5 deliverables (round 5 selection):
  vR5lg6Wr  iv120_x_short_heavy   SH=2.010
  KPn9akNl  iv30_x_short          SH=2.000
  9q9ro9le  iv60_x_short_long_z   SH=1.950
  YPN0dlQw  insider_x_iv120       SH=1.340
  78x1b3LQ  insider_x_iv90        SH=1.330
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


# For each base alpha, define the *signal-only* portion (pre-trade_when)
# in two robust-test variants: sign() wrap and 2-rank wrap.
DELIVERIES: list[tuple[str, str, str, dict, float]] = [
    # (label, base_alpha_id, expression, settings, baseline_SH)

    # 1. vR5lg6Wr / iv120_x_short_heavy
    ("iv120_short_heavy",
     "vR5lg6Wr",
     "iv = ts_backfill(implied_volatility_call_120 - implied_volatility_put_120, 5);\n"
     "supply = ts_backfill(mdl177_5shortsentimentfactor_lend_supply, 30);\n"
     "tightness = -ts_zscore(supply, 120);\n"
     "score = rank(iv) + 1.0 * rank(tightness);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(score, 5), -1)",
     {"decay": 6, "truncation": 0.02, "neutralization": "SUBINDUSTRY"},
     2.010),

    # 2. KPn9akNl / iv30_x_short
    ("iv30_short",
     "KPn9akNl",
     "iv = ts_backfill(implied_volatility_call_30 - implied_volatility_put_30, 5);\n"
     "supply = ts_backfill(mdl177_5shortsentimentfactor_lend_supply, 30);\n"
     "tightness = -ts_zscore(supply, 120);\n"
     "score = rank(iv) + 0.5 * rank(tightness);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(score, 5), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"},
     2.000),

    # 3. 9q9ro9le / iv60_x_short_long_z
    ("iv60_short_longz",
     "9q9ro9le",
     "iv = ts_backfill(implied_volatility_call_60 - implied_volatility_put_60, 5);\n"
     "supply = ts_backfill(mdl177_5shortsentimentfactor_lend_supply, 30);\n"
     "tightness = -ts_zscore(supply, 240);\n"
     "score = rank(iv) + 0.5 * rank(tightness);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, ts_decay_linear(score, 5), -1)",
     {"decay": 4, "truncation": 0.02, "neutralization": "SUBINDUSTRY"},
     1.950),

    # 4. YPN0dlQw / insider_x_iv120
    ("insider_x_iv120",
     "YPN0dlQw",
     "iv = ts_backfill(implied_volatility_call_120 - implied_volatility_put_120, 5);\n"
     "ins = ts_backfill(rp_css_insider, 30) + ts_backfill(rp_ess_insider, 30);\n"
     "score = ts_decay_linear(rank(iv) + rank(ins), 10);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, score, -1)",
     {"decay": 6, "truncation": 0.02, "neutralization": "SUBINDUSTRY"},
     1.340),

    # 5. 78x1b3LQ / insider_x_iv90
    ("insider_x_iv90",
     "78x1b3LQ",
     "iv = ts_backfill(implied_volatility_call_90 - implied_volatility_put_90, 5);\n"
     "ins = ts_backfill(rp_css_insider, 30) + ts_backfill(rp_ess_insider, 30);\n"
     "score = ts_decay_linear(rank(iv) + rank(ins), 10);\n"
     + NEWS_GATE + "\n"
     "trade_when(gate, score, -1)",
     {"decay": 6, "truncation": 0.02, "neutralization": "SUBINDUSTRY"},
     1.330),
]


def sign_variant(base_expr: str) -> str:
    """Replace the inner `score` expression with sign(rank(score)-0.5)
    so we test the alpha with magnitudes erased to {+1, 0, -1}."""
    # All 5 expressions are structured "score = ...;" then "trade_when(gate, ..., -1)"
    # We rewrap with sign() around the rank.
    # For the iv_x_short family the trade-side is `ts_decay_linear(score, 5)`.
    # For the insider family the trade-side IS `score` (which is already
    # `ts_decay_linear(rank(...)+rank(...), 10)`).
    # Simplest robust wrapper that works for both: wrap whatever follows
    # `trade_when(gate, ` with `sign(rank(...)-0.5)`.
    # We just textually rewrap: pre-image -> sign(rank(pre-image) - 0.5).
    head, _, tail = base_expr.partition("trade_when(gate, ")
    inner, _, rest = tail.rpartition(", -1)")
    new_inner = f"sign(rank({inner}) - 0.5)"
    return head + "trade_when(gate, " + new_inner + ", -1)" + rest


def rank2_variant(base_expr: str) -> str:
    """rank(rank(<signal>)) — collapse to a rank of a rank
    (still has magnitude info, but reranked)."""
    head, _, tail = base_expr.partition("trade_when(gate, ")
    inner, _, rest = tail.rpartition(", -1)")
    new_inner = f"rank(rank({inner}))"
    return head + "trade_when(gate, " + new_inner + ", -1)" + rest


def main():
    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")

    out_path = REPO / "WQ_COLD_FACTORS_ROBUSTNESS.json"
    rows = []

    for label, base_id, base_expr, settings, base_sh in DELIVERIES:
        log.info(f"=== {label} (baseline alpha {base_id}, base SH={base_sh:.3f}) ===")
        for tag, expr_builder in [("sign", sign_variant),
                                    ("rank2", rank2_variant)]:
            expr = expr_builder(base_expr)
            log.info(f"   [{tag}] expr: {expr.replace(chr(10), ' | ')}")
            res = submit(cm.session, f"{label}__{tag}", expr, settings)
            if not res.ok:
                log.warning(f"   [{tag}] FAILED: {res.error[:160]}")
                rows.append({"label": label, "tag": tag, "ok": False,
                              "base_sharpe": base_sh, "error": res.error})
                continue
            log.info(f"   [{tag}] SH={res.sharpe:+.3f} (vs base {base_sh:+.3f}) "
                      f"TO={res.turnover:.3f} chk={res.checks_passed}/{res.checks_total} "
                      f"alpha={res.alpha_id}")
            rows.append({
                "label": label, "tag": tag, "ok": True,
                "base_alpha_id": base_id,
                "base_sharpe": base_sh,
                "robust_alpha_id": res.alpha_id,
                "robust_sharpe": res.sharpe,
                "robust_turnover": res.turnover,
                "robust_fitness": res.fitness,
                "robust_checks": f"{res.checks_passed}/{res.checks_total}",
                "expression": expr,
            })
            with open(out_path, "w") as f:
                json.dump(rows, f, indent=2)

    print()
    print("=" * 100)
    print("rank/sign ROBUSTNESS REPORT")
    print(f"{'alpha':<22}{'tag':<7}{'base_SH':>9}{'robust_SH':>11}{'delta':>9}{'TO':>7}{'chk':>6}  verdict")
    for r in rows:
        if not r.get("ok"):
            print(f"{r['label']:<22}{r['tag']:<7}{r['base_sharpe']:>9.3f}"
                   f"{'-':>11}{'-':>9}{'-':>7}{'-':>6}  ERROR: {r.get('error','')[:40]}")
            continue
        delta = r["robust_sharpe"] - r["base_sharpe"]
        # >= -0.5 absolute is "robust"; >= 1.25 is "still deliverable"
        if r["robust_sharpe"] >= 1.25 and abs(delta) < 0.5:
            verdict = "ROBUST"
        elif r["robust_sharpe"] >= 1.25:
            verdict = "deliverable (large delta)"
        elif r["robust_sharpe"] >= 1.0:
            verdict = "marginal"
        else:
            verdict = "FRAGILE"
        print(f"{r['label']:<22}{r['tag']:<7}{r['base_sharpe']:>9.3f}"
               f"{r['robust_sharpe']:>11.3f}{delta:>+9.3f}{r['robust_turnover']:>7.3f}"
               f"{r['robust_checks']:>7}  {verdict}")
    print("=" * 100)
    with open(out_path, "w") as f:
        json.dump(rows, f, indent=2)
    log.info(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
