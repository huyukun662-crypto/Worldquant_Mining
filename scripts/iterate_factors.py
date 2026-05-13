"""Iterative WQ Brain mining: push WQ_SH towards 1.75.

Round 1: a batch of stronger composite expressions (multi-axis stacks +
alternative-data overlays). Each entry has its own settings.

Round 2 (manual gating after round 1): sweep settings on the top
expressions from round 1.

Output: WQ_ITERATION_RESULTS.json (appended incrementally so a crash
preserves data).

Usage:
    python scripts/iterate_factors.py --round 1
    python scripts/iterate_factors.py --round 2 --base-expr "<expr>"
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import sys
import time
from pathlib import Path

import requests as _requests
_orig_session_init = _requests.Session.__init__
def _patched_session_init(self, *a, **kw):
    _orig_session_init(self, *a, **kw)
    self.headers["User-Agent"] = "curl/8.5.0"
_requests.Session.__init__ = _patched_session_init

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("iterate")

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "worldquant-miner"
OUT = REPO / "WQ_ITERATION_RESULTS.json"

POLL_TIMEOUT_S = 900
POLL_INTERVAL_S = 5

# Survivor floor
SHARPE_FLOOR  = 1.75
TURNOVER_CEIL = 0.20
FITNESS_FLOOR = 1.25


def base_settings(**overrides):
    s = {
        "instrumentType":  "EQUITY",
        "region":          "USA",
        "universe":        "TOP3000",
        "delay":           1,
        "decay":           8,
        "neutralization":  "INDUSTRY",
        "truncation":      0.08,
        "pasteurization":  "ON",
        "unitHandling":    "VERIFY",
        "nanHandling":     "OFF",
        "language":        "FASTEXPR",
        "visualization":   False,
        "maxTrade":        "OFF",
        "testPeriod":      "P0Y0M",
    }
    s.update(overrides)
    return s


# =====================================================================
# Round 1: stronger composites built from columns with high alphaCount.
# Each combines value/quality/growth/cashflow/analyst axes that the
# literature shows are roughly orthogonal.
# =====================================================================
ROUND_1 = [
    # 1. Triple composite: B/M + ROA + E/P (value + quality + earnings)
    {
        "name": "r1_triple_value_quality_eps",
        "expression": (
            "add(add(group_rank(divide(equity, cap), subindustry),"
            " group_rank(divide(operating_income, assets), subindustry)),"
            " group_rank(divide(income, cap), subindustry))"
        ),
        "settings": base_settings(decay=8, neutralization="INDUSTRY",
                                  truncation=0.08, universe="TOP3000"),
    },
    # 2. ROIC: operating_income / (equity + debt)
    {
        "name": "r1_roic_smoothed",
        "expression": (
            "group_zscore(ts_mean(divide(operating_income, add(equity, debt)),"
            " 120), subindustry)"
        ),
        "settings": base_settings(decay=8, neutralization="SUBINDUSTRY",
                                  truncation=0.05, universe="TOP3000"),
    },
    # 3. FCF yield: (cashflow_op - capex) / cap
    {
        "name": "r1_fcf_yield",
        "expression": (
            "group_zscore(ts_mean(divide(subtract(cashflow_op, capex), cap),"
            " 120), subindustry)"
        ),
        "settings": base_settings(decay=8, neutralization="SUBINDUSTRY",
                                  truncation=0.05, universe="TOP3000"),
    },
    # 4. Quality × growth: ROA boosted, asset-growth penalized
    {
        "name": "r1_quality_minus_growth",
        "expression": (
            "subtract(group_rank(divide(operating_income, assets), subindustry),"
            " group_rank(divide(ts_delta(assets, 252), ts_mean(assets, 252)),"
            " subindustry))"
        ),
        "settings": base_settings(decay=8, neutralization="INDUSTRY",
                                  truncation=0.08, universe="TOP3000"),
    },
    # 5. Gross-margin (Novy-Marx pure): (revenue - cogs) / assets
    {
        "name": "r1_gross_profitability",
        "expression": (
            "group_zscore(ts_mean(divide(subtract(revenue, cogs), assets),"
            " 120), subindustry)"
        ),
        "settings": base_settings(decay=8, neutralization="SUBINDUSTRY",
                                  truncation=0.05, universe="TOP3000"),
    },
    # 6. EBIT yield (Greenblatt magic-formula style)
    {
        "name": "r1_ebit_yield",
        "expression": (
            "group_zscore(ts_mean(divide(ebit, cap), 120), subindustry)"
        ),
        "settings": base_settings(decay=8, neutralization="SUBINDUSTRY",
                                  truncation=0.05, universe="TOP3000"),
    },
    # 7. Earnings revision × analyst score × earnings surprise composite
    {
        "name": "r1_analyst_triple",
        "expression": (
            "add(add(group_rank(ts_mean(snt1_d1_earningsrevision, 22), industry),"
            " group_rank(snt1_cored1_score, industry)),"
            " group_rank(snt1_d1_netrecpercent, industry))"
        ),
        "settings": base_settings(decay=4, neutralization="INDUSTRY",
                                  truncation=0.05, universe="TOP1000"),
    },
    # 8. Mega-stack: value + quality - leverage + earnings yield + (negative) asset growth
    {
        "name": "r1_megastack_5axis",
        "expression": (
            "add(add(add(group_rank(divide(equity, cap), subindustry),"
            " group_rank(divide(operating_income, assets), subindustry)),"
            " group_rank(divide(income, cap), subindustry)),"
            " subtract(group_rank(divide(subtract(revenue, cogs), assets), subindustry),"
            " group_rank(divide(ts_delta(assets, 252), ts_mean(assets, 252)), subindustry)))"
        ),
        "settings": base_settings(decay=16, neutralization="INDUSTRY",
                                  truncation=0.08, universe="TOP3000"),
    },
]


# =====================================================================
# Round 3: EBIT-yield base (best of R1, SH=0.62 alone) crossed with
# orthogonal PV axes (momentum 12m, low-vol, short-term reversal).
# Each axis is empirically near-zero correlated with cross-sectional
# value/quality fundamentals, so stacking should add Sharpe.
# =====================================================================
EBIT_YIELD = "group_rank(ts_mean(divide(ebit, cap), 120), subindustry)"
MOM_12M    = "group_rank(ts_sum(returns, 240), subindustry)"
LOWVOL_60D = "-group_rank(ts_std_dev(returns, 60), subindustry)"
SHORT_REV  = "-group_rank(ts_sum(returns, 5), subindustry)"
ROA        = "group_rank(divide(operating_income, assets), subindustry)"

ROUND_3 = [
    # 1. EBIT + 12-month momentum
    {
        "name": "r3_ebit_x_mom12m",
        "expression": f"add({EBIT_YIELD}, {MOM_12M})",
        "settings": base_settings(decay=8, neutralization="INDUSTRY",
                                  truncation=0.08, universe="TOP3000"),
    },
    # 2. EBIT + low-volatility
    {
        "name": "r3_ebit_x_lowvol",
        "expression": f"add({EBIT_YIELD}, {LOWVOL_60D})",
        "settings": base_settings(decay=8, neutralization="INDUSTRY",
                                  truncation=0.08, universe="TOP3000"),
    },
    # 3. EBIT + short-term reversal (1-week)
    {
        "name": "r3_ebit_x_shortrev",
        "expression": f"add({EBIT_YIELD}, {SHORT_REV})",
        "settings": base_settings(decay=4, neutralization="INDUSTRY",
                                  truncation=0.05, universe="TOP3000"),
    },
    # 4. EBIT + momentum + low-vol (3-axis)
    {
        "name": "r3_ebit_mom_lowvol",
        "expression": f"add(add({EBIT_YIELD}, {MOM_12M}), {LOWVOL_60D})",
        "settings": base_settings(decay=8, neutralization="INDUSTRY",
                                  truncation=0.08, universe="TOP3000"),
    },
    # 5. Full 5-axis stack: value (EBIT) + quality (ROA) + momentum +
    #    low-vol + short-rev
    {
        "name": "r3_full5axis",
        "expression": (f"add(add(add(add({EBIT_YIELD}, {ROA}), {MOM_12M}),"
                       f" {LOWVOL_60D}), {SHORT_REV})"),
        "settings": base_settings(decay=8, neutralization="INDUSTRY",
                                  truncation=0.08, universe="TOP3000"),
    },
    # 6. Pure PV (no fundamentals): momentum + low-vol + short-rev
    #    -- baseline to see whether fundamentals add anything
    {
        "name": "r3_pure_pv",
        "expression": f"add(add({MOM_12M}, {LOWVOL_60D}), {SHORT_REV})",
        "settings": base_settings(decay=8, neutralization="INDUSTRY",
                                  truncation=0.08, universe="TOP3000"),
    },
]


# =====================================================================
# Round 4: lock in R3 winner (EBIT + 5d short reversal, SH=1.47 but
# TO=0.271 just over the 0.25 cap). Push TO under cap, then stack
# low-vol cleanly (NO mom12m, which we know is poison on this account).
# =====================================================================
SHORT_REV_5  = "-group_rank(ts_sum(returns, 5), subindustry)"
SHORT_REV_10 = "-group_rank(ts_sum(returns, 10), subindustry)"
SHORT_REV_22 = "-group_rank(ts_sum(returns, 22), subindustry)"
SHORT_REV_5_SMOOTH = "-group_rank(ts_decay_linear(ts_sum(returns, 5), 10), subindustry)"

ROUND_4 = [
    # 1. EBIT + 5d reversal, decay=16 (more setting-level smoothing)
    {
        "name": "r4_ebit_rev5_d16",
        "expression": f"add({EBIT_YIELD}, {SHORT_REV_5})",
        "settings": base_settings(decay=16, neutralization="INDUSTRY",
                                  truncation=0.08, universe="TOP3000"),
    },
    # 2. EBIT + 5d reversal, decay=32
    {
        "name": "r4_ebit_rev5_d32",
        "expression": f"add({EBIT_YIELD}, {SHORT_REV_5})",
        "settings": base_settings(decay=32, neutralization="INDUSTRY",
                                  truncation=0.08, universe="TOP3000"),
    },
    # 3. EBIT + 10d reversal (slower => lower TO)
    {
        "name": "r4_ebit_rev10",
        "expression": f"add({EBIT_YIELD}, {SHORT_REV_10})",
        "settings": base_settings(decay=8, neutralization="INDUSTRY",
                                  truncation=0.08, universe="TOP3000"),
    },
    # 4. EBIT + 22d reversal
    {
        "name": "r4_ebit_rev22",
        "expression": f"add({EBIT_YIELD}, {SHORT_REV_22})",
        "settings": base_settings(decay=8, neutralization="INDUSTRY",
                                  truncation=0.08, universe="TOP3000"),
    },
    # 5. EBIT + ts_decay_linear(5d reversal, 10) - smooth inside expr
    {
        "name": "r4_ebit_rev5_inner_decay10",
        "expression": f"add({EBIT_YIELD}, {SHORT_REV_5_SMOOTH})",
        "settings": base_settings(decay=8, neutralization="INDUSTRY",
                                  truncation=0.08, universe="TOP3000"),
    },
    # 6. EBIT + 5d reversal + low-vol (3-axis, NO mom)
    {
        "name": "r4_ebit_rev5_lowvol",
        "expression": f"add(add({EBIT_YIELD}, {SHORT_REV_5}), {LOWVOL_60D})",
        "settings": base_settings(decay=8, neutralization="INDUSTRY",
                                  truncation=0.08, universe="TOP3000"),
    },
    # 7. EBIT + 10d reversal + low-vol, decay=16 (the conservative stack)
    {
        "name": "r4_ebit_rev10_lowvol_d16",
        "expression": f"add(add({EBIT_YIELD}, {SHORT_REV_10}), {LOWVOL_60D})",
        "settings": base_settings(decay=16, neutralization="INDUSTRY",
                                  truncation=0.08, universe="TOP3000"),
    },
    # 8. Pure 5d reversal alone (baseline: how much SH does shortrev have?)
    {
        "name": "r4_shortrev_only",
        "expression": SHORT_REV_5,
        "settings": base_settings(decay=8, neutralization="INDUSTRY",
                                  truncation=0.08, universe="TOP3000"),
    },
]


# =====================================================================
# Round 5: keep the R3 winner expression (EBIT + 5d short reversal,
# SH=1.47 TO=0.271), vary ONLY truncation / neutralization / universe
# to push TO under 0.25 without smoothing the signal. From R2 we
# already know these axes leave 0.62 EBIT-only signal unchanged
# (so a similar invariance may give us SH ~ 1.47 with TO < 0.25).
# =====================================================================
R3_WINNER_EXPR = f"add({EBIT_YIELD}, {SHORT_REV_5})"

ROUND_5 = [
    # 1. higher truncation 0.10 (cap extreme position weights)
    {
        "name": "r5_ebit_rev5_trunc010",
        "expression": R3_WINNER_EXPR,
        "settings": base_settings(decay=8, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000"),
    },
    # 2. trunc 0.15
    {
        "name": "r5_ebit_rev5_trunc015",
        "expression": R3_WINNER_EXPR,
        "settings": base_settings(decay=8, neutralization="INDUSTRY",
                                  truncation=0.15, universe="TOP3000"),
    },
    # 3. SUBINDUSTRY neutralization (tighter group)
    {
        "name": "r5_ebit_rev5_subind",
        "expression": R3_WINNER_EXPR,
        "settings": base_settings(decay=8, neutralization="SUBINDUSTRY",
                                  truncation=0.08, universe="TOP3000"),
    },
    # 4. SUBINDUSTRY + trunc 0.10
    {
        "name": "r5_ebit_rev5_subind_trunc010",
        "expression": R3_WINNER_EXPR,
        "settings": base_settings(decay=8, neutralization="SUBINDUSTRY",
                                  truncation=0.10, universe="TOP3000"),
    },
    # 5. SECTOR + trunc 0.10
    {
        "name": "r5_ebit_rev5_sector_trunc010",
        "expression": R3_WINNER_EXPR,
        "settings": base_settings(decay=8, neutralization="SECTOR",
                                  truncation=0.10, universe="TOP3000"),
    },
    # 6. trunc 0.10 with pasteurization OFF (less artificial flattening
    #    of the signal across same-name observations)
    {
        "name": "r5_ebit_rev5_trunc010_nopast",
        "expression": R3_WINNER_EXPR,
        "settings": base_settings(decay=8, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 7. multi-window reversal: average of 3,5,7-day returns. Smoother
    #    on TO than raw 5-day; may keep SH high.
    {
        "name": "r5_ebit_rev_multi357",
        "expression": (
            f"add({EBIT_YIELD},"
            f" -group_rank(add(add(ts_sum(returns, 3),"
            f" ts_sum(returns, 5)), ts_sum(returns, 7)), subindustry))"
        ),
        "settings": base_settings(decay=8, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000"),
    },
    # 8. ts_zscore-based 5-day reversal (name-history normalized,
    #    not cross-sectional rank)
    {
        "name": "r5_ebit_revz5",
        "expression": (
            f"add({EBIT_YIELD},"
            f" -group_rank(ts_zscore(ts_sum(returns, 5), 60), subindustry))"
        ),
        "settings": base_settings(decay=8, neutralization="INDUSTRY",
                                  truncation=0.08, universe="TOP3000"),
    },
]


# =====================================================================
# Round 6: combine R5's pasteurization=OFF insight with R3#3's original
# trunc=0.08, plus test new orthogonal axes (volume z-score, 3-day rev).
# =====================================================================
SHORT_REV_3 = "-group_rank(ts_sum(returns, 3), subindustry)"
VOL_ZSCORE  = "group_rank(ts_zscore(volume, 60), subindustry)"
ADV_ZSCORE  = "group_rank(ts_zscore(adv20, 60), subindustry)"

ROUND_6 = [
    # 1. R3#3 expr + pasteurization=OFF + trunc=0.08
    {
        "name": "r6_ebit_rev5_nopast_t008",
        "expression": R3_WINNER_EXPR,
        "settings": base_settings(decay=8, neutralization="INDUSTRY",
                                  truncation=0.08, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 2. Same + lower decay (decay=4)
    {
        "name": "r6_ebit_rev5_nopast_d4_t010",
        "expression": R3_WINNER_EXPR,
        "settings": base_settings(decay=4, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 3. 3-day reversal (more aggressive) + pasteurization=OFF + trunc=0.10
    {
        "name": "r6_ebit_rev3_nopast",
        "expression": f"add({EBIT_YIELD}, {SHORT_REV_3})",
        "settings": base_settings(decay=8, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 4. EBIT + rev5 + volume z-score (new orthogonal axis)
    {
        "name": "r6_ebit_rev5_volz",
        "expression": f"add(add({EBIT_YIELD}, {SHORT_REV_5}), {VOL_ZSCORE})",
        "settings": base_settings(decay=8, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 5. EBIT + rev5 + adv20 z-score (alt liquidity axis)
    {
        "name": "r6_ebit_rev5_advz",
        "expression": f"add(add({EBIT_YIELD}, {SHORT_REV_5}), {ADV_ZSCORE})",
        "settings": base_settings(decay=8, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 6. EBIT + rev5, SUBINDUSTRY + pasteurization=OFF + trunc=0.08
    {
        "name": "r6_ebit_rev5_subind_nopast_t008",
        "expression": R3_WINNER_EXPR,
        "settings": base_settings(decay=8, neutralization="SUBINDUSTRY",
                                  truncation=0.08, universe="TOP3000",
                                  pasteurization="OFF"),
    },
]


# =====================================================================
# Round 7: stack the R6 winners (rev3, adv20-z) and explore decay
# axis where the SH-TO Pareto is steep (d=4 -> 1.59 / 0.282; d=8 ->
# 1.54 / 0.170 with adv20-z helping).
# =====================================================================
EBIT_REV3_ADVZ = f"add(add({EBIT_YIELD}, {SHORT_REV_3}), {ADV_ZSCORE})"
EBIT_REV5_ADVZ = f"add(add({EBIT_YIELD}, {SHORT_REV_5}), {ADV_ZSCORE})"

ROUND_7 = [
    # 1. ebit + rev3 + adv20-z (main stack of R6's two winners)
    {
        "name": "r7_ebit_rev3_advz",
        "expression": EBIT_REV3_ADVZ,
        "settings": base_settings(decay=8, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 2. same, decay=4 (push SH higher; we know adv20-z helps TO)
    {
        "name": "r7_ebit_rev3_advz_d4",
        "expression": EBIT_REV3_ADVZ,
        "settings": base_settings(decay=4, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 3. ebit + rev5 + adv20-z, decay=4 (chase R6#1's SH 1.59 with vol axis)
    {
        "name": "r7_ebit_rev5_advz_d4",
        "expression": EBIT_REV5_ADVZ,
        "settings": base_settings(decay=4, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 4. ebit + rev3 + adv20-z, SUBINDUSTRY
    {
        "name": "r7_ebit_rev3_advz_subind",
        "expression": EBIT_REV3_ADVZ,
        "settings": base_settings(decay=8, neutralization="SUBINDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 5. ebit + rev3 + adv20-z + vol-z (4-axis stack of all winners)
    {
        "name": "r7_full4axis",
        "expression": (
            f"add(add(add({EBIT_YIELD}, {SHORT_REV_3}), {ADV_ZSCORE}),"
            f" {VOL_ZSCORE})"
        ),
        "settings": base_settings(decay=8, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 6. ebit + (rev3+rev5)/2 + adv20-z (multi-window reversal stack)
    {
        "name": "r7_ebit_rev35_advz",
        "expression": (
            f"add(add(add({EBIT_YIELD}, {SHORT_REV_3}), {SHORT_REV_5}),"
            f" {ADV_ZSCORE})"
        ),
        "settings": base_settings(decay=8, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
]


# =====================================================================
# Round 8: fine-grain decay sweep (5, 6, 7) on R7 winners; try smaller
# universes; try outer zscore wrap for FIT push.
# R7 best: ebit+rev3+adv20-z d=4 SH=2.02 TO=0.287 FIT=1.41
#          ebit+rev3+adv20-z d=8 SH=1.74 TO=0.181 FIT=1.40
# decay 5-7 should land in the SH 1.8-1.95 / TO 0.20-0.27 sweet spot.
# =====================================================================
ROUND_8 = [
    # 1. ebit+rev3+adv20-z, decay=5
    {
        "name": "r8_rev3_advz_d5",
        "expression": EBIT_REV3_ADVZ,
        "settings": base_settings(decay=5, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 2. decay=6
    {
        "name": "r8_rev3_advz_d6",
        "expression": EBIT_REV3_ADVZ,
        "settings": base_settings(decay=6, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 3. decay=7
    {
        "name": "r8_rev3_advz_d7",
        "expression": EBIT_REV3_ADVZ,
        "settings": base_settings(decay=7, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 4. ebit+rev5+adv20-z d=5 (push FIT on the rev5 variant)
    {
        "name": "r8_rev5_advz_d5",
        "expression": EBIT_REV5_ADVZ,
        "settings": base_settings(decay=5, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 5. 4-axis (vol+adv20) d=5
    {
        "name": "r8_4axis_d5",
        "expression": (
            f"add(add(add({EBIT_YIELD}, {SHORT_REV_3}), {ADV_ZSCORE}),"
            f" {VOL_ZSCORE})"
        ),
        "settings": base_settings(decay=5, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 6. ebit+rev3+adv20-z d=4 TOP1000 (denser universe might lift FIT)
    {
        "name": "r8_rev3_advz_d4_TOP1000",
        "expression": EBIT_REV3_ADVZ,
        "settings": base_settings(decay=4, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP1000",
                                  pasteurization="OFF"),
    },
]


# =====================================================================
# Round 9: one fundamental + one option + one sentiment factor.
# Different data axes than R1-R8 (which were dominated by EBIT/rev/adv).
# Per-factor settings independent.
# =====================================================================
ROUND_9 = [
    # ------------------------------------------------------------------
    # 1. FUNDAMENTAL -- Net Profit Margin (income / sales), smoothed
    #    120 days. Different ratio than EBIT/cap. Captures margin
    #    quality, less collinear with size/value than ROA or EBIT yield.
    # ------------------------------------------------------------------
    {
        "name": "r9_net_profit_margin",
        "category": "fundamental",
        "expression": (
            "group_zscore(ts_mean(divide(income, sales), 120), subindustry)"
        ),
        "settings": base_settings(decay=8, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },

    # ------------------------------------------------------------------
    # 2. OPTION -- IV Skew (call IV / put IV at 270d). High value =
    #    market priced more upside than downside = bullish positioning.
    #    Smaller universe because option data coverage is ~0.70.
    # ------------------------------------------------------------------
    {
        "name": "r9_iv_skew_callput270",
        "category": "option",
        "expression": (
            "group_rank(ts_mean(divide(implied_volatility_call_270,"
            " implied_volatility_put_270), 22), sector)"
        ),
        "settings": base_settings(decay=8, neutralization="SECTOR",
                                  truncation=0.10, universe="TOP1000",
                                  pasteurization="OFF"),
    },

    # ------------------------------------------------------------------
    # 3. SENTIMENT -- Social-media sentiment momentum (22d). Bullish
    #    social sentiment that *sustains* (rolling mean) predicts up.
    #    scl12 has full coverage (1.00) so we can stay on TOP3000.
    # ------------------------------------------------------------------
    {
        "name": "r9_social_sentiment_mom",
        "category": "sentiment",
        "expression": (
            "group_rank(ts_mean(scl12_sentiment, 22), industry)"
        ),
        "settings": base_settings(decay=4, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
]


# =====================================================================
# Round 10: tighter filter (TO < 0.15). Strategy:
#   * stack IV-skew (R9#2: SH=0.61, TO=0.047) as a 4th ultra-low-TO axis
#     -- mathematically lowers blended TO proportionally
#   * sweep decay 9, 10, 12 on the R7/R8 winning expression to walk
#     down the decay-Pareto curve toward TO < 0.15
# =====================================================================
IV_SKEW = ("group_rank(ts_mean(divide(implied_volatility_call_270,"
           " implied_volatility_put_270), 22), sector)")
EBIT_REV3_ADVZ_IVSKEW = (
    f"add(add(add({EBIT_YIELD}, {SHORT_REV_3}), {ADV_ZSCORE}), {IV_SKEW})"
)

ROUND_10 = [
    # 1. R7 winner + IV-skew (4th low-TO axis)
    {
        "name": "r10_rev3_advz_ivskew_d5",
        "expression": EBIT_REV3_ADVZ_IVSKEW,
        "settings": base_settings(decay=5, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 2. d=8
    {
        "name": "r10_rev3_advz_ivskew_d8",
        "expression": EBIT_REV3_ADVZ_IVSKEW,
        "settings": base_settings(decay=8, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 3. Walk decay axis: d=10 on rev3+adv20-z (no IV) to bridge d=8 (TO=0.181)
    #    and d=16 (TO=0.111)
    {
        "name": "r10_rev3_advz_d10",
        "expression": EBIT_REV3_ADVZ,
        "settings": base_settings(decay=10, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 4. d=12 on rev3+adv20-z
    {
        "name": "r10_rev3_advz_d12",
        "expression": EBIT_REV3_ADVZ,
        "settings": base_settings(decay=12, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 5. rev5 variant + IV-skew + d=8
    {
        "name": "r10_rev5_advz_ivskew_d8",
        "expression": (
            f"add(add(add({EBIT_YIELD}, {SHORT_REV_5}), {ADV_ZSCORE}),"
            f" {IV_SKEW})"
        ),
        "settings": base_settings(decay=8, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 6. rev3+adv20-z+iv-skew, d=10 (denser smoothing on the 4-axis)
    {
        "name": "r10_rev3_advz_ivskew_d10",
        "expression": EBIT_REV3_ADVZ_IVSKEW,
        "settings": base_settings(decay=10, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
]


# =====================================================================
# Round 11: one factor from each non-PV category per the user's UI
# breakdown (Analyst, Fundamental, Model, News, Option, Social Media).
# Each independent (no stacking with prior winners yet) so we can
# measure the per-axis edge before composing.
# =====================================================================
ROUND_11 = [
    # ANALYST  -- announced EBIT financial value / market cap, smoothed
    {
        "name": "r11_analyst_ebit_yield",
        "category": "analyst",
        "expression": (
            "group_zscore(ts_mean(divide(anl4_ebit_value, cap), 60), subindustry)"
        ),
        "settings": base_settings(decay=8, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # FUNDAMENTAL -- asset turnover (sales / assets), smoothed.
    # Not yet tested; orthogonal to ROA / E-yield (margin x turnover).
    {
        "name": "r11_fund_asset_turnover",
        "category": "fundamental",
        "expression": (
            "group_zscore(ts_mean(divide(sales, assets), 120), subindustry)"
        ),
        "settings": base_settings(decay=8, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # MODEL -- low idiosyncratic risk premium (90d unsystematic risk).
    # User UI marks Model category value-score=7 (highest).
    {
        "name": "r11_model_low_idio_risk",
        "category": "model",
        "expression": (
            "-group_rank(ts_mean(unsystematic_risk_last_90_days, 22), subindustry)"
        ),
        "settings": base_settings(decay=8, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # MODEL (alt) -- pre-built value-vs-price ratio rank.
    {
        "name": "r11_model_garp_vp_ratio",
        "category": "model",
        "expression": (
            "group_rank(ts_mean(mdl177_garpanalystmodel_qgp_vfpriceratio, 22),"
            " subindustry)"
        ),
        "settings": base_settings(decay=8, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # NEWS -- composite sentiment of business news, 22d smoothed
    {
        "name": "r11_news_business_sentiment",
        "category": "news",
        "expression": (
            "group_rank(ts_mean(rp_css_business, 22), industry)"
        ),
        "settings": base_settings(decay=4, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # OPTION -- short-dated IV mean-reversion. High 10d IV historically
    # reverts (negative carries).
    {
        "name": "r11_option_iv10_revert",
        "category": "option",
        "expression": (
            "-group_rank(ts_zscore(implied_volatility_mean_10, 60), sector)"
        ),
        "settings": base_settings(decay=8, neutralization="SECTOR",
                                  truncation=0.10, universe="TOP1000",
                                  pasteurization="OFF"),
    },
    # SOCIAL MEDIA -- buzz extreme fade (contrarian on viral names)
    {
        "name": "r11_social_buzz_fade",
        "category": "socialmedia",
        "expression": (
            "-group_rank(ts_zscore(scl12_buzz, 22), industry)"
        ),
        "settings": base_settings(decay=4, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
]


# =====================================================================
# Round 12: replace fundamental EBIT with analyst EBIT (+0.30 SH alone)
# and add -garp_vp_ratio (R11 sign-flipped +1.12 TO 0.019) as a new
# ultra-low-TO axis.
# =====================================================================
ANL_EBIT_YIELD = (
    "group_zscore(ts_mean(divide(anl4_ebit_value, cap), 60), subindustry)"
)
GARP_FLIP = (
    "-group_rank(ts_mean(mdl177_garpanalystmodel_qgp_vfpriceratio, 22),"
    " subindustry)"
)
ASSET_TURNOVER = (
    "group_zscore(ts_mean(divide(sales, assets), 120), subindustry)"
)

ROUND_12 = [
    # 1. R10 winner with EBIT base replaced by analyst-EBIT
    #    expr = anlEBIT + rev3 + adv20-z + iv-skew  (4-axis, d=10)
    {
        "name": "r12_anlebit_rev3_advz_ivskew_d10",
        "expression": (
            f"add(add(add({ANL_EBIT_YIELD}, {SHORT_REV_3}),"
            f" {ADV_ZSCORE}), {IV_SKEW})"
        ),
        "settings": base_settings(decay=10, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 2. d=8 variant of #1
    {
        "name": "r12_anlebit_rev3_advz_ivskew_d8",
        "expression": (
            f"add(add(add({ANL_EBIT_YIELD}, {SHORT_REV_3}),"
            f" {ADV_ZSCORE}), {IV_SKEW})"
        ),
        "settings": base_settings(decay=8, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 3. 5-axis: anlEBIT + rev3 + adv20-z + iv-skew + (-)garp
    {
        "name": "r12_5axis_anlebit_garp_d10",
        "expression": (
            f"add(add(add(add({ANL_EBIT_YIELD}, {SHORT_REV_3}),"
            f" {ADV_ZSCORE}), {IV_SKEW}), {GARP_FLIP})"
        ),
        "settings": base_settings(decay=10, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 4. 5-axis at d=8 (potentially highest SH config)
    {
        "name": "r12_5axis_anlebit_garp_d8",
        "expression": (
            f"add(add(add(add({ANL_EBIT_YIELD}, {SHORT_REV_3}),"
            f" {ADV_ZSCORE}), {IV_SKEW}), {GARP_FLIP})"
        ),
        "settings": base_settings(decay=8, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 5. 6-axis: add asset turnover too
    {
        "name": "r12_6axis_anlebit_garp_turnover_d10",
        "expression": (
            f"add(add(add(add(add({ANL_EBIT_YIELD}, {SHORT_REV_3}),"
            f" {ADV_ZSCORE}), {IV_SKEW}), {GARP_FLIP}), {ASSET_TURNOVER})"
        ),
        "settings": base_settings(decay=10, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 6. -garp replacing iv-skew (test whether garp is a better 4th axis)
    {
        "name": "r12_anlebit_rev3_advz_garp_d10",
        "expression": (
            f"add(add(add({ANL_EBIT_YIELD}, {SHORT_REV_3}),"
            f" {ADV_ZSCORE}), {GARP_FLIP})"
        ),
        "settings": base_settings(decay=10, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
]


# =====================================================================
# Round 13: push SH past 2.0 while keeping TO < 0.20 AND FIT > 1.25.
# decay-axis Pareto on (fundEBIT+rev3+adv20-z+iv-skew):
#   d=5  SH 2.22  TO 0.224  (FAILS TO)
#   d=8  SH 2.02  TO 0.163  (PASS, current best at SH>=2)
#   d=10 SH 1.92  TO 0.140  (PASS)
# Target: d=6/7 sweet spot. Plus 5-axis with R11 flipped-IV10 momentum.
# =====================================================================
FLIPPED_IV10 = "-group_rank(ts_zscore(implied_volatility_mean_10, 60), sector)"
# NOTE: R11 found this SH=-0.87, so flipped sign (drop the leading -)
# is the +0.87 momentum signal. Wrap as a momentum (positive) axis:
IV10_MOMENTUM = "group_rank(ts_zscore(implied_volatility_mean_10, 60), sector)"

ROUND_13 = [
    # 1. R10 4-axis at decay=6 (between d=5 fail and d=8 pass)
    {
        "name": "r13_rev3_advz_ivskew_d6",
        "expression": EBIT_REV3_ADVZ_IVSKEW,
        "settings": base_settings(decay=6, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 2. d=7
    {
        "name": "r13_rev3_advz_ivskew_d7",
        "expression": EBIT_REV3_ADVZ_IVSKEW,
        "settings": base_settings(decay=7, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 3. + iv-mean-10 momentum (R11 flipped, SH=0.87 alone)
    {
        "name": "r13_5axis_iv10mom_d8",
        "expression": (
            f"add(add(add(add({EBIT_YIELD}, {SHORT_REV_3}),"
            f" {ADV_ZSCORE}), {IV_SKEW}), {IV10_MOMENTUM})"
        ),
        "settings": base_settings(decay=8, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 4. 5-axis at d=6 (where 4-axis lands at sweet spot)
    {
        "name": "r13_5axis_iv10mom_d6",
        "expression": (
            f"add(add(add(add({EBIT_YIELD}, {SHORT_REV_3}),"
            f" {ADV_ZSCORE}), {IV_SKEW}), {IV10_MOMENTUM})"
        ),
        "settings": base_settings(decay=6, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 5. tighter truncation 0.08 on R10 4-axis d=8 (might lower TO)
    {
        "name": "r13_rev3_advz_ivskew_d8_t008",
        "expression": EBIT_REV3_ADVZ_IVSKEW,
        "settings": base_settings(decay=8, neutralization="INDUSTRY",
                                  truncation=0.08, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 6. trunc 0.05 (more concentrated; may push SH up if winners are
    #    in the tail)
    {
        "name": "r13_rev3_advz_ivskew_d6_t008",
        "expression": EBIT_REV3_ADVZ_IVSKEW,
        "settings": base_settings(decay=6, neutralization="INDUSTRY",
                                  truncation=0.08, universe="TOP3000",
                                  pasteurization="OFF"),
    },
]


# =====================================================================
# Round 14: 3 fresh Model-category factors (different from R11's
# unsystematic_risk and garp_vp_ratio). Three diverse axes:
#   * value      -- 5y relative leading EPS yield
#   * composite  -- FANGMA growth-profitability model
#   * liquidity  -- short-interest ratio
# Each standalone first, then sign decided by result.
# =====================================================================
ROUND_14 = [
    # 1. VALUE -- 5-year relative leading 12m EPS yield (mdl177)
    {
        "name": "r14_model_5y_rel_eps_yield",
        "category": "model_value",
        "expression": (
            "group_rank(ts_mean(mdl177_2_5yearrelativevaluefactor_rel5yfwdep,"
            " 22), subindustry)"
        ),
        "settings": base_settings(decay=8, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 2. COMPOSITE -- FANGMA growth/profit (full coverage)
    {
        "name": "r14_model_fangma_gpam11",
        "category": "model_composite",
        "expression": (
            "group_rank(ts_mean(mdl177_fangma_gpam_usa_fangma_gpam11, 22),"
            " subindustry)"
        ),
        "settings": base_settings(decay=8, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 3. LIQUIDITY RISK -- short-interest ratio (fade crowded shorts)
    {
        "name": "r14_model_si_ratio_fade",
        "category": "model_liquidity",
        "expression": (
            "-group_rank(ts_mean(mdl177_2_liquidityriskfactor_si_ratio, 22),"
            " subindustry)"
        ),
        "settings": base_settings(decay=8, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
]


# =====================================================================
# Round 15: 3 News-category factors. Three subtypes:
#   * earnings news sentiment
#   * analyst-ratings news sentiment (event-score variant)
#   * news-driven max up-move (post-news momentum)
# =====================================================================
ROUND_15 = [
    # 1. Earnings news composite sentiment, 22d mean
    {
        "name": "r15_news_earnings_sentiment",
        "category": "news",
        "expression": (
            "group_rank(ts_mean(rp_css_earnings, 22), industry)"
        ),
        "settings": base_settings(decay=8, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 2. Analyst ratings event-sentiment score, 22d
    {
        "name": "r15_news_ratings_ess",
        "category": "news",
        "expression": (
            "group_rank(ts_mean(rp_ess_ratings, 22), industry)"
        ),
        "settings": base_settings(decay=8, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 3. News-driven max up-return -- post-news momentum (stocks that
    #    spike on news continue up). Lower neutralization (sector) to
    #    let event-driven mid-caps through.
    {
        "name": "r15_news_max_up_ret_mom",
        "category": "news",
        "expression": (
            "group_rank(ts_mean(news_max_up_ret, 22), sector)"
        ),
        "settings": base_settings(decay=8, neutralization="SECTOR",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
]


# =====================================================================
# Round 16: fresh News fields + stack rp_ess_ratings (R15 +0.28) into
# R13 winner to test whether News axis adds SH/FIT.
# =====================================================================
ESS_RATINGS = "group_rank(ts_mean(rp_ess_ratings, 22), industry)"

ROUND_16 = [
    # 1. News-derived PE fade (-news_pe_ratio): low PE = value
    {
        "name": "r16_news_pe_fade",
        "expression": (
            "-group_rank(ts_mean(news_pe_ratio, 22), subindustry)"
        ),
        "settings": base_settings(decay=8, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 2. News-derived ATR14 low-vol premium (-z-score)
    {
        "name": "r16_news_atr14_lowvol",
        "expression": (
            "-group_rank(ts_zscore(news_atr14, 60), subindustry)"
        ),
        "settings": base_settings(decay=8, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 3. Quick-spike momentum: shorter time-to-10% up = stronger
    {
        "name": "r16_news_mins10_pctup",
        "expression": (
            "-group_rank(ts_mean(news_mins_10_pct_up, 22), subindustry)"
        ),
        "settings": base_settings(decay=8, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 4. Investor-relations news impact projection
    {
        "name": "r16_news_nip_investor",
        "expression": (
            "group_rank(ts_mean(rp_nip_inverstor, 22), industry)"
        ),
        "settings": base_settings(decay=8, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 5. R13 winner + rp_ess_ratings as 5th axis, d=6 (push SH past 2.2?)
    {
        "name": "r16_r13winner_plus_essratings_d6",
        "expression": (
            f"add(add(add(add({EBIT_YIELD}, {SHORT_REV_3}), {ADV_ZSCORE}),"
            f" {IV_SKEW}), {ESS_RATINGS})"
        ),
        "settings": base_settings(decay=6, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 6. Same stack d=8 (TO-friendly)
    {
        "name": "r16_r13winner_plus_essratings_d8",
        "expression": (
            f"add(add(add(add({EBIT_YIELD}, {SHORT_REV_3}), {ADV_ZSCORE}),"
            f" {IV_SKEW}), {ESS_RATINGS})"
        ),
        "settings": base_settings(decay=8, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
]


# =====================================================================
# Round 17: push SH past 2.4 by adding R16's strongest standalone news
# signal (-news_pe_ratio: SH=0.81 TO=0.036) as 6th axis to akNvjWRR.
# Also try flipped 5y_eps as alternative axis.
# =====================================================================
NEWS_PE_FADE  = "-group_rank(ts_mean(news_pe_ratio, 22), subindustry)"
FLIP_5Y_EPS   = ("-group_rank(ts_mean(mdl177_2_5yearrelativevaluefactor_rel5yfwdep,"
                 " 22), subindustry)")
R16_BASE_5AXIS = (
    f"add(add(add(add({EBIT_YIELD}, {SHORT_REV_3}), {ADV_ZSCORE}),"
    f" {IV_SKEW}), {ESS_RATINGS})"
)

ROUND_17 = [
    # 1. 6-axis: akNvjWRR + (-news_pe), d=6
    {
        "name": "r17_6axis_newspe_d6",
        "expression": f"add({R16_BASE_5AXIS}, {NEWS_PE_FADE})",
        "settings": base_settings(decay=6, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 2. d=7
    {
        "name": "r17_6axis_newspe_d7",
        "expression": f"add({R16_BASE_5AXIS}, {NEWS_PE_FADE})",
        "settings": base_settings(decay=7, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 3. d=8
    {
        "name": "r17_6axis_newspe_d8",
        "expression": f"add({R16_BASE_5AXIS}, {NEWS_PE_FADE})",
        "settings": base_settings(decay=8, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 4. 6-axis: akNvjWRR + flipped_5y_eps (model value axis), d=6
    {
        "name": "r17_6axis_5yeps_d6",
        "expression": f"add({R16_BASE_5AXIS}, {FLIP_5Y_EPS})",
        "settings": base_settings(decay=6, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 5. 7-axis: + both (-news_pe) and flipped_5y_eps
    {
        "name": "r17_7axis_d6",
        "expression": (
            f"add(add({R16_BASE_5AXIS}, {NEWS_PE_FADE}), {FLIP_5Y_EPS})"
        ),
        "settings": base_settings(decay=6, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 6. d=5 6-axis (chase highest SH)
    {
        "name": "r17_6axis_newspe_d5",
        "expression": f"add({R16_BASE_5AXIS}, {NEWS_PE_FADE})",
        "settings": base_settings(decay=5, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
]


def _load(p, name):
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def submit(session, expression, settings):
    body = {"type": "REGULAR", "settings": settings, "regular": expression}
    log.info(f"-> {expression[:90]}")
    log.info(f"   {settings}")
    # POST with retry on 429 + transient network errors
    r = None
    for attempt in range(5):
        try:
            r = session.post("https://api.worldquantbrain.com/simulations",
                             json=body, timeout=30)
        except _requests.exceptions.RequestException as e:
            log.warning(f"   POST error: {e}; retry {attempt+1}/5 in 10s")
            time.sleep(10); continue
        if r.status_code == 429:
            time.sleep(float(r.headers.get("Retry-After") or 30)); continue
        break
    if r is None or r.status_code != 201:
        return {"ok": False, "stage": "submit",
                "status": getattr(r, "status_code", None),
                "body": (r.text[:300] if r is not None else "no response")}
    progress = r.headers.get("Location")
    if not progress:
        return {"ok": False, "stage": "submit", "error": "no Location"}
    t0 = time.time()
    last = ""
    while time.time() - t0 < POLL_TIMEOUT_S:
        time.sleep(POLL_INTERVAL_S)
        try:
            rp = session.get(progress, timeout=30)
        except _requests.exceptions.RequestException as e:
            log.warning(f"   poll network error: {type(e).__name__}; retry")
            continue
        if rp.status_code == 429:
            time.sleep(30); continue
        if rp.status_code != 200:
            continue
        try:
            d = rp.json()
        except ValueError:
            continue
        st = d.get("status", "")
        if st != last:
            log.info(f"   status={st} ({int(time.time()-t0)}s)")
            last = st
        if st == "COMPLETE":
            aid = d.get("alpha")
            try:
                ra = session.get(f"https://api.worldquantbrain.com/alphas/{aid}",
                                  timeout=30)
            except _requests.exceptions.RequestException as e:
                return {"ok": False, "stage": "alpha-get-network",
                        "alpha_id": aid, "error": str(e)[:200]}
            if ra.status_code != 200:
                return {"ok": False, "stage": "alpha-get",
                        "status": ra.status_code, "alpha_id": aid}
            return {"ok": True, "alpha_id": aid, "alpha": ra.json()}
        if st in ("ERROR", "FAILED", "WARNING"):
            return {"ok": False, "stage": "sim", "status": st,
                    "message": (d.get("message") or "")[:300]}
    return {"ok": False, "stage": "timeout"}


def run_batch(session, batch, append_to=None):
    out = list(append_to or [])
    # Skip-resume: a batch member whose (name, expression, settings) is
    # already in `out` is not re-submitted -- preserves R3 progress
    # across crashes / retries.
    done_keys = {(r.get("name"), r.get("expression"),
                  json.dumps(r.get("settings"), sort_keys=True))
                 for r in out if r.get("ok")}
    for i, f in enumerate(batch, 1):
        key = (f["name"], f["expression"],
               json.dumps(f["settings"], sort_keys=True))
        if key in done_keys:
            log.info(f"=== [{i}/{len(batch)}] {f['name']}  [SKIP: already done]")
            continue
        log.info(f"=== [{i}/{len(batch)}] {f['name']} ===")
        try:
            res = submit(session, f["expression"], f["settings"])
        except Exception as e:
            log.error(f"   submit() crashed: {type(e).__name__}: {e}")
            res = {"ok": False, "stage": "exception",
                   "error": f"{type(e).__name__}: {str(e)[:200]}"}
        rec = {"name": f["name"], "expression": f["expression"],
               "settings": f["settings"]}
        if res.get("ok"):
            a = res["alpha"]; isb = a.get("is") or {}
            checks = isb.get("checks") or []
            rec.update({
                "ok": True, "alpha_id": res["alpha_id"],
                "sharpe":   isb.get("sharpe"),
                "turnover": isb.get("turnover"),
                "fitness":  isb.get("fitness"),
                "returns":  isb.get("returns"),
                "drawdown": isb.get("drawdown"),
                "longCount":  isb.get("longCount"),
                "shortCount": isb.get("shortCount"),
                "checks_passed": sum(1 for c in checks if c.get("result") == "PASS"),
                "checks_total":  len(checks),
            })
            sh = rec["sharpe"] or 0.0
            to = rec["turnover"] or 0.0
            fit = rec["fitness"] or 0.0
            rec["survivor"] = bool(sh >= SHARPE_FLOOR and to < TURNOVER_CEIL
                                   and fit > FITNESS_FLOOR)
            log.info(f"   OK alpha={res['alpha_id']} SH={sh:+.3f} "
                     f"TO={to:.3f} FIT={fit:+.3f} "
                     f"{'PASS' if rec['survivor'] else 'fail'}")
        else:
            rec.update({"ok": False, **res, "survivor": False})
            log.warning(f"   ERR {res}")
        out.append(rec)
        with open(OUT, "w") as fp:
            json.dump(out, fp, indent=2)
    return out


def sweep_settings(base_expr: str, base_name: str):
    """Round-2 setting sweep around a base expression."""
    variants = []
    grid = [
        # (decay, neut, trunc, universe)
        ( 4,  "INDUSTRY",     0.05, "TOP3000"),
        ( 8,  "INDUSTRY",     0.10, "TOP3000"),
        (16,  "INDUSTRY",     0.08, "TOP3000"),
        (32,  "INDUSTRY",     0.08, "TOP3000"),
        ( 8,  "SUBINDUSTRY",  0.05, "TOP3000"),
        ( 8,  "SECTOR",       0.05, "TOP3000"),
        ( 8,  "INDUSTRY",     0.05, "TOP1000"),
        ( 8,  "INDUSTRY",     0.05, "TOP500"),
        (16,  "SUBINDUSTRY",  0.05, "TOP1000"),
    ]
    for (decay, neut, trunc, univ) in grid:
        variants.append({
            "name": f"{base_name}_d{decay}_{neut}_t{trunc}_{univ}",
            "expression": base_expr,
            "settings": base_settings(decay=decay, neutralization=neut,
                                       truncation=trunc, universe=univ),
        })
    return variants


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--round", type=int, required=True)
    ap.add_argument("--base-expr", type=str, default="")
    ap.add_argument("--base-name", type=str, default="sweep")
    args = ap.parse_args()

    cm_mod = _load(VENDOR / "core" / "credential_manager.py", "cm")
    cm = cm_mod.CredentialManager(base_path=str(REPO))
    # Sandbox TLS-inspection CA rotates the server cert ~hourly; auth
    # immediately after a rotation fails with "certificate not yet
    # valid". Retry a few times with backoff.
    auth_ok = False
    for attempt in range(6):
        if cm.authenticate(auto_load=True, auto_prompt=False):
            auth_ok = True; break
        wait = 10 + 5 * attempt
        log.warning(f"   auth attempt {attempt+1}/6 failed; sleep {wait}s")
        time.sleep(wait)
    if not auth_ok:
        log.error("auth failed after retries"); return 2
    log.info(f"authenticated as {cm.credentials.username}")

    existing = []
    if OUT.exists():
        existing = json.load(open(OUT))

    if args.round == 1:
        batch = ROUND_1
    elif args.round == 2:
        if not args.base_expr:
            log.error("round 2 needs --base-expr"); return 2
        batch = sweep_settings(args.base_expr, args.base_name)
    elif args.round == 3:
        batch = ROUND_3
    elif args.round == 4:
        batch = ROUND_4
    elif args.round == 5:
        batch = ROUND_5
    elif args.round == 6:
        batch = ROUND_6
    elif args.round == 7:
        batch = ROUND_7
    elif args.round == 8:
        batch = ROUND_8
    elif args.round == 9:
        batch = ROUND_9
    elif args.round == 10:
        batch = ROUND_10
    elif args.round == 11:
        batch = ROUND_11
    elif args.round == 12:
        batch = ROUND_12
    elif args.round == 13:
        batch = ROUND_13
    elif args.round == 14:
        batch = ROUND_14
    elif args.round == 15:
        batch = ROUND_15
    elif args.round == 16:
        batch = ROUND_16
    elif args.round == 17:
        batch = ROUND_17
    else:
        log.error(f"unknown round {args.round}"); return 2

    log.info(f"round {args.round}: {len(batch)} submissions "
             f"(budget ~{len(batch) * 200 / 60:.0f} min @ ~200s/sim)")
    results = run_batch(cm.session, batch, append_to=existing)

    # Sort by SH desc
    ok = [r for r in results if r.get("ok")]
    ok.sort(key=lambda r: r.get("sharpe") or -99, reverse=True)
    print()
    print("=" * 130)
    print(f"All-time top-10 (Filter: SH >= {SHARPE_FLOOR} AND TO < {TURNOVER_CEIL} AND FIT > {FITNESS_FLOOR}):")
    print("=" * 130)
    print(f"{'#':<3}{'name':<46}{'SH':>7}{'TO':>7}{'FIT':>7}{'flt':>5}  alpha_id   expression")
    for i, r in enumerate(ok[:10], 1):
        sh = r.get('sharpe', 0) or 0
        to = r.get('turnover', 0) or 0
        fit = r.get('fitness', 0) or 0
        flt = "PASS" if r.get("survivor") else "fail"
        print(f"{i:<3}{r['name'][:45]:<46}{sh:7.3f}{to:7.3f}{fit:7.3f} {flt:>4}"
              f"  {r.get('alpha_id','-'):<10} {r['expression'][:60]}")
    print("=" * 130)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
