"""D0 round 3: push fundamentals past SH>1.25 via the proven SH-booster
structure -- news-regime gate + signed_power amplification -- applied
to the strongest fundamental6 signals.

All delay=0, cold fields (fundamental6 + news12 gate, NO options).

Strongest base signals from fund6 round:
  capex/assets  +0.85 SH (empirically positive in this universe; f6.5
                was -rank => -0.85, so +rank => +0.85)
  gross profit  +0.44 SH (Novy-Marx)
  value (book/price)  -- classic
The gate concentrates trading on high-news-attention days; signed_power
amplifies extreme cross-sectional ranks.  This lifted weak signals to
SH>2 in prior (delay=1) work.
"""

from __future__ import annotations
import json
import sys
from pathlib import Path
from dataclasses import asdict

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mine_cold_fields import (  # noqa: E402
    CandidateResult, submit, fetch_self_corr, _load, VENDOR, REPO, log,
)

GATE = ("gate = (ts_backfill(news_pct_90min, 5) < 1) * "
        "(ts_rank(abs(news_pct_30min), 60) > 0.80);")

# fundamental6 building blocks (all wrapped in ts_backfill 250)
GP   = "divide(ts_backfill(revenue,250)-ts_backfill(cogs,250), ts_backfill(assets,250))"
ROA  = "ts_backfill(return_assets,250)"
INV  = "divide(ts_backfill(capex,250), ts_backfill(assets,250))"
CFO  = "divide(ts_backfill(cashflow_op,250), ts_backfill(assets,250))"
BV   = "divide(ts_backfill(bookvalue_ps,250), close)"
ACC  = "divide(ts_backfill(income,250)-ts_backfill(cashflow_op,250), ts_backfill(assets,250))"


CANDIDATES: list[tuple[str, str, dict]] = [

    # 1. capex(+) amplified + news gate (strongest single signal)
    ("g3_1_capex_gate_amp",
     f"s = group_zscore({INV}, subindustry);\n" + GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(s, 3), 5), -1)",
     {"decay": 4, "truncation": 0.05, "neutralization": "SUBINDUSTRY"}),

    # 2. GP amplified + news gate
    ("g3_2_gp_gate_amp",
     f"s = group_zscore({GP}, subindustry);\n" + GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(s, 3), 5), -1)",
     {"decay": 4, "truncation": 0.05, "neutralization": "SUBINDUSTRY"}),

    # 3. capex(+) + GP composite amplified + gate
    ("g3_3_capex_gp_gate",
     f"s = group_zscore({INV}, subindustry) + group_zscore({GP}, subindustry);\n"
     + GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(s - 0, 3), 5), -1)",
     {"decay": 4, "truncation": 0.05, "neutralization": "SUBINDUSTRY"}),

    # 4. value (book/price) amplified + gate
    ("g3_4_value_gate_amp",
     f"s = group_zscore({BV}, subindustry);\n" + GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(s, 3), 5), -1)",
     {"decay": 4, "truncation": 0.05, "neutralization": "SUBINDUSTRY"}),

    # 5. capex(+) + GP + value triple, amplified + gate
    ("g3_5_triple_gate",
     f"s = group_zscore({INV}, subindustry) + group_zscore({GP}, subindustry) "
     f"+ 0.5*group_zscore({BV}, subindustry);\n" + GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(s, 3), 5), -1)",
     {"decay": 4, "truncation": 0.05, "neutralization": "SUBINDUSTRY"}),

    # 6. capex(+) amplified, news gate, signed_power 5 (stronger amp)
    ("g3_6_capex_amp5",
     f"s = group_zscore({INV}, subindustry);\n" + GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(s, 5), 5), -1)",
     {"decay": 4, "truncation": 0.05, "neutralization": "SUBINDUSTRY"}),

    # 7. quality (GP+ROA+CFO-ACC) + capex(+), amplified + gate
    ("g3_7_quality_capex_gate",
     f"q = group_zscore({GP},subindustry)+group_zscore({ROA},subindustry)"
     f"+group_zscore({CFO},subindustry)-group_zscore({ACC},subindustry);\n"
     f"s = q + group_zscore({INV}, subindustry);\n" + GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(s, 3), 5), -1)",
     {"decay": 6, "truncation": 0.05, "neutralization": "SUBINDUSTRY"}),

    # 8. capex(+) amplified + gate, TOP1000 (tighter universe)
    ("g3_8_capex_top1000",
     f"s = group_zscore({INV}, subindustry);\n" + GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(s, 3), 5), -1)",
     {"decay": 4, "truncation": 0.05, "neutralization": "SUBINDUSTRY",
      "universe": "TOP1000"}),

    # 9. capex(+) + GP amplified + gate, INDUSTRY neut + decay8
    ("g3_9_capex_gp_industry",
     f"s = group_zscore({INV}, industry) + group_zscore({GP}, industry);\n"
     + GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(s, 3), 5), -1)",
     {"decay": 8, "truncation": 0.05, "neutralization": "INDUSTRY"}),

    # 10. capex(+) raw rank amplified + gate (rank not zscore)
    ("g3_10_capex_rank_amp",
     f"s = group_rank({INV}, subindustry) - 0.5;\n" + GATE + "\n"
     "trade_when(gate, ts_decay_linear(signed_power(s, 3), 5), -1)",
     {"decay": 4, "truncation": 0.05, "neutralization": "SUBINDUSTRY"}),
]


def main():
    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        log.error("authentication failed"); return 2
    log.info(f"authenticated as {cm.credentials.username}")

    out_path = REPO / "WQ_D0_GATED.json"
    results: list[CandidateResult] = []
    for i, (family, expr, settings) in enumerate(CANDIDATES, 1):
        s = dict(settings); s["delay"] = 0; s.setdefault("universe", "TOP3000")
        log.info(f"=== g3 [{i}/{len(CANDIDATES)}] family={family} ===")
        log.info(f"   expr: {expr.replace(chr(10), ' | ')}")
        res = submit(cm.session, family, expr, s)
        results.append(res)
        if not res.ok:
            log.warning(f"   FAILED: {res.error[:160]}")
        else:
            log.info(f"   SH={res.sharpe:+.3f} TO={res.turnover:.3f} "
                      f"FIT={res.fitness:+.3f} checks={res.checks_passed}/{res.checks_total} "
                      f"alpha={res.alpha_id}")
        with open(out_path, "w") as f:
            json.dump([asdict(r) for r in results], f, indent=2)

    log.info("=== pass 2: self-correlation ===")
    for r in results:
        if not r.ok or not r.alpha_id: continue
        sc, top, st = fetch_self_corr(cm.session, r.alpha_id, timeout_s=90)
        r.self_corr = sc
        if top:
            r.self_corr_peer = top.get("id"); r.self_corr_peer_sharpe = top.get("sharpe")
        log.info(f"   {r.alpha_id} self_corr={sc} ({st})")
    with open(out_path, "w") as f:
        json.dump([asdict(r) for r in results], f, indent=2)

    def submittable(r):
        # all gating checks pass; SELF_CORRELATION may be PENDING but
        # must not be FAIL; require known sc < 0.7 if available
        if not r.ok: return False
        if any(c.get("result") == "FAIL" for c in r.checks): return False
        if r.self_corr is not None and abs(r.self_corr) >= 0.7: return False
        return r.sharpe > 1.25 and r.fitness >= 1.0 and r.turnover < 0.25

    ok = sorted([r for r in results if r.ok], key=lambda r: r.sharpe, reverse=True)
    print("\n" + "=" * 120)
    print(f"D0 gated round: {len(ok)}/{len(results)} OK   "
          f"submittable: {sum(1 for r in ok if submittable(r))}")
    print(f"{'#':<4}{'family':<24}{'SH':>7}{'TO':>7}{'FIT':>7}{'chk':>6}{'sc':>7} {'SUBMIT?':<8} alpha_id")
    for i, r in enumerate(ok, 1):
        sc = f"{r.self_corr:+.3f}" if r.self_corr is not None else "  -  "
        mark = "YES-SUBMIT" if submittable(r) else "no"
        print(f"{i:<4}{r.family:<24}{r.sharpe:7.3f}{r.turnover:7.3f}{r.fitness:7.3f}"
               f"{r.checks_passed:>3}/{r.checks_total:<2}{sc:>7} {mark:<8} {r.alpha_id}")
    for r in [r for r in results if not r.ok]:
        print(f"  FAIL {r.family:<22} {r.error[:90]}")
    print("=" * 120)
    log.info(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
