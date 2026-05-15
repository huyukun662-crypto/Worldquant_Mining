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
SHARPE_FLOOR  = 1.5
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


# =====================================================================
# Round 18: push SH past 2.4 with TRULY orthogonal axes (not value
# duplicates). R17 confirmed value-side additions dilute. R18 tries:
#   * pure decay push d=4/5 on R16 base 5-axis
#   * non-value extension: rev2 (different time-scale reversal)
#   * iv10 momentum (different option tenor than iv-skew 270d)
# =====================================================================
SHORT_REV_2 = "-group_rank(ts_sum(returns, 2), subindustry)"

ROUND_18 = [
    # 1. R16 base (5-axis) d=5 -- push SH
    {
        "name": "r18_r16base_d5",
        "expression": R16_BASE_5AXIS,
        "settings": base_settings(decay=5, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 2. R16 base d=4 (most aggressive)
    {
        "name": "r18_r16base_d4",
        "expression": R16_BASE_5AXIS,
        "settings": base_settings(decay=4, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 3. 6-axis with rev2 added (different reversal tenor)
    {
        "name": "r18_6axis_rev2_d6",
        "expression": f"add({R16_BASE_5AXIS}, {SHORT_REV_2})",
        "settings": base_settings(decay=6, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 4. 6-axis with flipped iv10-mom (different option tenor)
    {
        "name": "r18_6axis_iv10mom_d6",
        "expression": f"add({R16_BASE_5AXIS}, {IV10_MOMENTUM})",
        "settings": base_settings(decay=6, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 5. 6-axis with iv10-mom at d=8 (heavier smoothing since iv10 has TO)
    {
        "name": "r18_6axis_iv10mom_d8",
        "expression": f"add({R16_BASE_5AXIS}, {IV10_MOMENTUM})",
        "settings": base_settings(decay=8, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 6. 7-axis: rev2 + iv10mom both -- maximum orthogonal stack
    {
        "name": "r18_7axis_rev2_iv10mom_d6",
        "expression": (
            f"add(add({R16_BASE_5AXIS}, {SHORT_REV_2}), {IV10_MOMENTUM})"
        ),
        "settings": base_settings(decay=6, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
]


# =====================================================================
# Round 19: TO-tightening sweep on the SH>2.3 configs from R18.
# Levers: truncation 0.05/0.08, SUBINDUSTRY, TOP1000.
# Goal: keep SH > 2.2 while bringing TO < 0.20.
# =====================================================================
ROUND_19 = [
    # 1. R18#1 (d=5 5-axis) + trunc=0.05
    {
        "name": "r19_r16base_d5_t005",
        "expression": R16_BASE_5AXIS,
        "settings": base_settings(decay=5, neutralization="INDUSTRY",
                                  truncation=0.05, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 2. R18#1 d=5 + SUBINDUSTRY
    {
        "name": "r19_r16base_d5_subind",
        "expression": R16_BASE_5AXIS,
        "settings": base_settings(decay=5, neutralization="SUBINDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 3. R18#1 d=5 + TOP1000
    {
        "name": "r19_r16base_d5_top1000",
        "expression": R16_BASE_5AXIS,
        "settings": base_settings(decay=5, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP1000",
                                  pasteurization="OFF"),
    },
    # 4. R18#5 (+iv10mom d=8) + trunc=0.05  (SH 2.17 TO 0.210 -- trunc may push TO under)
    {
        "name": "r19_iv10mom_d8_t005",
        "expression": f"add({R16_BASE_5AXIS}, {IV10_MOMENTUM})",
        "settings": base_settings(decay=8, neutralization="INDUSTRY",
                                  truncation=0.05, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 5. R18#1 d=5 + trunc=0.05 + SUBINDUSTRY (stacked TO-tighteners)
    {
        "name": "r19_r16base_d5_t005_subind",
        "expression": R16_BASE_5AXIS,
        "settings": base_settings(decay=5, neutralization="SUBINDUSTRY",
                                  truncation=0.05, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 6. d=4 + trunc=0.05 (aggressive both directions)
    {
        "name": "r19_r16base_d4_t005",
        "expression": R16_BASE_5AXIS,
        "settings": base_settings(decay=4, neutralization="INDUSTRY",
                                  truncation=0.05, universe="TOP3000",
                                  pasteurization="OFF"),
    },
]


# =====================================================================
# Round 20: shift the Pareto curve by replacing fund EBIT with analyst
# EBIT in the 5-axis (akNvjWRR class). R12 found anlEBIT 4-axis has
# ~30% lower TO at similar SH; if the same shift applies to 5-axis,
# d=5 anlEBIT-5axis may land at SH 2.20+ AND TO < 0.20.
# =====================================================================
ANLEBIT_5AXIS = (
    f"add(add(add(add({ANL_EBIT_YIELD}, {SHORT_REV_3}), {ADV_ZSCORE}),"
    f" {IV_SKEW}), {ESS_RATINGS})"
)

ROUND_20 = [
    # 1. anlEBIT 5-axis d=5 (key candidate)
    {
        "name": "r20_anl5axis_d5",
        "expression": ANLEBIT_5AXIS,
        "settings": base_settings(decay=5, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 2. anlEBIT 5-axis d=6 (direct comparison to akNvjWRR)
    {
        "name": "r20_anl5axis_d6",
        "expression": ANLEBIT_5AXIS,
        "settings": base_settings(decay=6, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 3. anlEBIT 5-axis d=8 (TO-safe)
    {
        "name": "r20_anl5axis_d8",
        "expression": ANLEBIT_5AXIS,
        "settings": base_settings(decay=8, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 4. anlEBIT 5-axis d=4 (most aggressive)
    {
        "name": "r20_anl5axis_d4",
        "expression": ANLEBIT_5AXIS,
        "settings": base_settings(decay=4, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 5. fund-EBIT 5-axis with rev5 instead of rev3 (less aggressive reversal)
    {
        "name": "r20_fundrev5_5axis_d6",
        "expression": (
            f"add(add(add(add({EBIT_YIELD}, {SHORT_REV_5}), {ADV_ZSCORE}),"
            f" {IV_SKEW}), {ESS_RATINGS})"
        ),
        "settings": base_settings(decay=6, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 6. fund-EBIT 5-axis with IV-skew 120d (different option tenor)
    {
        "name": "r20_iv120skew_5axis_d6",
        "expression": (
            f"add(add(add(add({EBIT_YIELD}, {SHORT_REV_3}), {ADV_ZSCORE}),"
            f" group_rank(ts_mean(divide(implied_volatility_call_120,"
            f" implied_volatility_put_120), 22), sector)),"
            f" {ESS_RATINGS})"
        ),
        "settings": base_settings(decay=6, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
]


# =====================================================================
# Round 21: aggressive STRUCTURAL variants on R16_BASE_5AXIS to break
# the SH=2.26 wall. The previous rounds confirmed setting tweaks and
# add-stacking are exhausted -- this round changes how axes combine.
# =====================================================================
ROUND_21 = [
    # 1. Winsorize the whole 5-axis composite (cap tails)
    {
        "name": "r21_winsorize_wrap_d6",
        "expression": f"winsorize({R16_BASE_5AXIS}, std=4)",
        "settings": base_settings(decay=6, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 2. zscore wrap (centers and scales final composite)
    {
        "name": "r21_zscore_wrap_d6",
        "expression": f"zscore({R16_BASE_5AXIS})",
        "settings": base_settings(decay=6, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 3. rank wrap (re-rank composite, smooth tails)
    {
        "name": "r21_rank_wrap_d6",
        "expression": f"rank({R16_BASE_5AXIS})",
        "settings": base_settings(decay=6, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 4. Multiply value x reversal (interaction term, plus rest of stack)
    #    Long stocks that are BOTH cheap AND just sold off.
    {
        "name": "r21_value_x_rev_d6",
        "expression": (
            f"add(add(add(multiply({EBIT_YIELD}, {SHORT_REV_3}),"
            f" {ADV_ZSCORE}), {IV_SKEW}), {ESS_RATINGS})"
        ),
        "settings": base_settings(decay=6, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 5. signed_power dampening
    {
        "name": "r21_signed_power_d6",
        "expression": f"signed_power({R16_BASE_5AXIS}, 0.7)",
        "settings": base_settings(decay=6, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 6. scale (long-side / short-side normalized to booksize)
    {
        "name": "r21_scale_wrap_d6",
        "expression": f"scale({R16_BASE_5AXIS})",
        "settings": base_settings(decay=6, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
]


# =====================================================================
# Round 22: 6 NEW-LOGIC factors. NONE reuse the EBIT/rev3/adv20-z/
# IV-skew/ess_ratings family. Each is a different anomaly:
# =====================================================================
ROUND_22 = [
    # 1. INTRADAY GAP REVERSAL -- stocks that close below the open
    #    (gap-down) tend to mean-revert. signal = -(open-close)/close
    {
        "name": "r22_open_close_gap_revert",
        "expression": (
            "group_rank(ts_mean(divide(subtract(close, open), close), 22),"
            " subindustry)"
        ),
        "settings": base_settings(decay=6, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 2. VWAP DEVIATION REVERSAL -- close above 60d-vwap fades
    {
        "name": "r22_vwap_deviation_revert",
        "expression": (
            "-group_rank(divide(close, ts_mean(vwap, 60)), subindustry)"
        ),
        "settings": base_settings(decay=6, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 3. LIQUIDITY-WEIGHTED REVERSAL -- short-term reversal is stronger
    #    in low-volatility names (interaction, not stack)
    {
        "name": "r22_liq_weighted_rev",
        "expression": (
            "multiply(-group_rank(ts_sum(returns, 5), subindustry),"
            " -group_rank(ts_std_dev(returns, 60), subindustry))"
        ),
        "settings": base_settings(decay=6, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 4. EARNINGS-SURPRISE COMPOSITE (analyst-only, no price)
    #    earnings surprise + revision + net target percent
    {
        "name": "r22_earnings_surprise_composite",
        "expression": (
            "add(add(group_rank(ts_mean(snt1_d1_earningssurprise, 22), industry),"
            " group_rank(ts_mean(snt1_d1_earningsrevision, 22), industry)),"
            " group_rank(snt1_d1_nettargetpercent, industry))"
        ),
        "settings": base_settings(decay=4, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP1000",
                                  pasteurization="OFF"),
    },
    # 5. PIOTROSKI-STYLE QUALITY × LOW-GROWTH
    #    Strong margins (revenue-cogs)/assets minus aggressive asset growth
    {
        "name": "r22_gross_minus_asset_growth",
        "expression": (
            "subtract(group_zscore(ts_mean(divide(subtract(revenue, cogs), assets),"
            " 120), subindustry),"
            " group_zscore(divide(ts_delta(assets, 252), ts_mean(assets, 252)),"
            " subindustry))"
        ),
        "settings": base_settings(decay=8, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 6. BETA-NEUTRAL MOMENTUM -- 12m return rank within beta deciles
    #    (cross-section momentum after removing market exposure)
    {
        "name": "r22_beta_neutral_momentum",
        "expression": (
            "group_neutralize(group_rank(ts_sum(returns, 240), subindustry),"
            " bucket(rank(beta_last_360_days_spy), range='0,1,0.1'))"
        ),
        "settings": base_settings(decay=8, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
]


# =====================================================================
# Round 23: build a FRESH composite using R22's positive standalones,
# explicitly NOT reusing rev3 / adv20-z / IV-skew / ess_ratings (the
# akNvjWRR family). Goal: produce another SH>=1.75/TO<0.20/FIT>1.25
# alpha from a DIFFERENT axis set.
# =====================================================================
VWAP_REVERT      = "-group_rank(divide(close, ts_mean(vwap, 60)), subindustry)"
OPEN_CLOSE_CONT  = ("group_rank(ts_mean(divide(subtract(close, open), close), 22),"
                    " subindustry)")
QUALITY_MINUS_GROWTH = (
    "subtract(group_zscore(ts_mean(divide(subtract(revenue, cogs), assets),"
    " 120), subindustry),"
    " group_zscore(divide(ts_delta(assets, 252), ts_mean(assets, 252)),"
    " subindustry))"
)
LIQ_REV_FLIP = (
    "multiply(group_rank(ts_sum(returns, 5), subindustry),"
    " -group_rank(ts_std_dev(returns, 60), subindustry))"
)

ROUND_23 = [
    # 1. 3-axis pure R22: vwap_revert + quality-growth + open_close_cont
    {
        "name": "r23_3axis_pure_r22",
        "expression": (
            f"add(add({VWAP_REVERT}, {QUALITY_MINUS_GROWTH}), {OPEN_CLOSE_CONT})"
        ),
        "settings": base_settings(decay=6, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 2. 4-axis pure R22: + flipped liq-weighted rev
    {
        "name": "r23_4axis_pure_r22",
        "expression": (
            f"add(add(add({VWAP_REVERT}, {QUALITY_MINUS_GROWTH}),"
            f" {OPEN_CLOSE_CONT}), {LIQ_REV_FLIP})"
        ),
        "settings": base_settings(decay=6, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 3. 4-axis: pure R22 + EBIT yield (4 totally different axes than R20)
    {
        "name": "r23_4axis_r22_plus_ebit",
        "expression": (
            f"add(add(add({VWAP_REVERT}, {QUALITY_MINUS_GROWTH}),"
            f" {OPEN_CLOSE_CONT}), {EBIT_YIELD})"
        ),
        "settings": base_settings(decay=6, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 4. 5-axis: + EBIT + (-)garp (the deep value flip from R11)
    {
        "name": "r23_5axis_r22_ebit_garp",
        "expression": (
            f"add(add(add(add({VWAP_REVERT}, {QUALITY_MINUS_GROWTH}),"
            f" {OPEN_CLOSE_CONT}), {EBIT_YIELD}),"
            f" -group_rank(ts_mean(mdl177_garpanalystmodel_qgp_vfpriceratio, 22),"
            f" subindustry))"
        ),
        "settings": base_settings(decay=6, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 5. d=4 of 3-axis (push SH)
    {
        "name": "r23_3axis_d4",
        "expression": (
            f"add(add({VWAP_REVERT}, {QUALITY_MINUS_GROWTH}), {OPEN_CLOSE_CONT})"
        ),
        "settings": base_settings(decay=4, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 6. 5-axis at d=4 (maximum aggressive)
    {
        "name": "r23_5axis_d4",
        "expression": (
            f"add(add(add(add({VWAP_REVERT}, {QUALITY_MINUS_GROWTH}),"
            f" {OPEN_CLOSE_CONT}), {EBIT_YIELD}),"
            f" -group_rank(ts_mean(mdl177_garpanalystmodel_qgp_vfpriceratio, 22),"
            f" subindustry))"
        ),
        "settings": base_settings(decay=4, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
]


# =====================================================================
# Round 24: SLOW-only composite using 3 model-value sign-flipped
# factors. Each had SH ~+1.12 TO 0.02 standalone (R11/R14). Stacking
# them with EBIT and asset_turnover may produce a fundamentally
# different alpha than the rev3-centric akNvjWRR family.
# =====================================================================
FLIP_5Y       = ("-group_rank(ts_mean(mdl177_2_5yearrelativevaluefactor_rel5yfwdep,"
                 " 22), subindustry)")
FLIP_GARP     = ("-group_rank(ts_mean(mdl177_garpanalystmodel_qgp_vfpriceratio,"
                 " 22), subindustry)")
FLIP_FANGMA11 = ("-group_rank(ts_mean(mdl177_fangma_gpam_usa_fangma_gpam11,"
                 " 22), subindustry)")
ASSET_TURNOVER_R11 = (
    "group_zscore(ts_mean(divide(sales, assets), 120), subindustry)"
)

ROUND_24 = [
    # 1. 3 model-flips stacked
    {
        "name": "r24_3model_flips_d8",
        "expression": f"add(add({FLIP_5Y}, {FLIP_GARP}), {FLIP_FANGMA11})",
        "settings": base_settings(decay=8, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 2. + EBIT yield (4 slow axes)
    {
        "name": "r24_3model_plus_ebit_d8",
        "expression": (
            f"add(add(add({FLIP_5Y}, {FLIP_GARP}), {FLIP_FANGMA11}),"
            f" {EBIT_YIELD})"
        ),
        "settings": base_settings(decay=8, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 3. + EBIT + asset_turnover (5 slow axes)
    {
        "name": "r24_5slow_d8",
        "expression": (
            f"add(add(add(add({FLIP_5Y}, {FLIP_GARP}), {FLIP_FANGMA11}),"
            f" {EBIT_YIELD}), {ASSET_TURNOVER_R11})"
        ),
        "settings": base_settings(decay=8, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 4. + iv-skew (slow but option-side)
    {
        "name": "r24_5slow_iv_d8",
        "expression": (
            f"add(add(add(add({FLIP_5Y}, {FLIP_GARP}), {FLIP_FANGMA11}),"
            f" {EBIT_YIELD}), {IV_SKEW})"
        ),
        "settings": base_settings(decay=8, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 5. 3-flip + analystEBIT (replace fund-EBIT with anlEBIT)
    {
        "name": "r24_3model_plus_anlebit_d8",
        "expression": (
            f"add(add(add({FLIP_5Y}, {FLIP_GARP}), {FLIP_FANGMA11}),"
            f" {ANL_EBIT_YIELD})"
        ),
        "settings": base_settings(decay=8, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 6. d=4 (push SH)
    {
        "name": "r24_5slow_iv_d4",
        "expression": (
            f"add(add(add(add({FLIP_5Y}, {FLIP_GARP}), {FLIP_FANGMA11}),"
            f" {EBIT_YIELD}), {IV_SKEW})"
        ),
        "settings": base_settings(decay=4, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
]


# =====================================================================
# Round 25: alternative FAST signals (not rev3) combined with the R24
# slow stack. Each is a different reversal/continuation primitive.
# =====================================================================
FAST_CLOSE_Z   = "-group_rank(ts_zscore(close, 22), subindustry)"
FAST_RET_Z5    = "-group_rank(ts_zscore(returns, 5), subindustry)"
FAST_ARGMAX22  = "group_rank(ts_arg_max(returns, 22), subindustry)"
SLOW_3FLIPS    = f"add(add({FLIP_5Y}, {FLIP_GARP}), {FLIP_FANGMA11})"

ROUND_25 = [
    # 1. close-z fade + 3 model-flips (4 axes, all NEW logic)
    {
        "name": "r25_closez_slow_d6",
        "expression": f"add({FAST_CLOSE_Z}, {SLOW_3FLIPS})",
        "settings": base_settings(decay=6, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 2. ret-z5 fade + 3 model-flips
    {
        "name": "r25_retz5_slow_d6",
        "expression": f"add({FAST_RET_Z5}, {SLOW_3FLIPS})",
        "settings": base_settings(decay=6, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 3. arg_max + 3 model-flips
    {
        "name": "r25_argmax_slow_d6",
        "expression": f"add({FAST_ARGMAX22}, {SLOW_3FLIPS})",
        "settings": base_settings(decay=6, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 4. close-z fade + 3 model-flips + IV-skew (5-axis)
    {
        "name": "r25_closez_slow_iv_d6",
        "expression": (
            f"add(add({FAST_CLOSE_Z}, {SLOW_3FLIPS}), {IV_SKEW})"
        ),
        "settings": base_settings(decay=6, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 5. All R22 useful + 3 model-flips (large composite, mixed logic)
    {
        "name": "r25_r22_plus_3flips_d6",
        "expression": (
            f"add(add(add(add({VWAP_REVERT}, {QUALITY_MINUS_GROWTH}),"
            f" {OPEN_CLOSE_CONT}), {FLIP_5Y}), {FLIP_GARP})"
        ),
        "settings": base_settings(decay=6, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 6. R25#4 at d=4 (push SH)
    {
        "name": "r25_closez_slow_iv_d4",
        "expression": (
            f"add(add({FAST_CLOSE_Z}, {SLOW_3FLIPS}), {IV_SKEW})"
        ),
        "settings": base_settings(decay=4, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
]


# =====================================================================
# Round 26: TRULY different structural primitives. No `add()` stack of
# ranks. Each factor uses a fundamentally different combinator:
#   * ts_corr-based   -- cross-series correlation as signal
#   * divide composite -- ratio of two ranks
#   * sign-gated      -- one signal gates another's direction
#   * ts_delta-based  -- discrete change operators
#   * group_mean diff -- sector-relative deviation
# =====================================================================
ROUND_26 = [
    # 1. RETURN-VOLUME DIVERGENCE -- ts_corr(returns, volume, 22) signal:
    #    high correlation = buying climax = fade (negative).
    {
        "name": "r26_ret_vol_corr_fade",
        "expression": (
            "-group_rank(ts_corr(returns, volume, 22), subindustry)"
        ),
        "settings": base_settings(decay=6, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 2. CLOSE-VWAP DIVERGENCE -- close persistently above vwap fades
    #    via ts_corr (where positive corr = close tracks vwap, fade
    #    when diverging via negative coef rank).
    {
        "name": "r26_close_vwap_corr",
        "expression": (
            "-group_rank(ts_corr(close, vwap, 22), subindustry)"
        ),
        "settings": base_settings(decay=6, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 3. SIGN-GATED REVERSAL -- only fade reversal in cheap names:
    #    multiply(sign(EBIT_rank - 0.5), -reversal). Cheap names get
    #    long signal on selloff, expensive names get nothing.
    {
        "name": "r26_sign_gated_rev",
        "expression": (
            "multiply(sign(subtract(group_rank(ts_mean(divide(ebit, cap), 120),"
            " subindustry), 0.5)),"
            " -group_rank(ts_sum(returns, 5), subindustry))"
        ),
        "settings": base_settings(decay=6, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 4. RATIO COMPOSITE -- return/risk (Sharpe-like) ratio
    {
        "name": "r26_return_over_risk",
        "expression": (
            "divide(group_rank(ts_sum(returns, 22), subindustry),"
            " group_rank(ts_std_dev(returns, 60), subindustry))"
        ),
        "settings": base_settings(decay=6, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 5. ts_delta REVERSAL -- 5-day discrete change in close, faded
    {
        "name": "r26_ts_delta_close_fade",
        "expression": (
            "-group_rank(ts_delta(close, 5), subindustry)"
        ),
        "settings": base_settings(decay=6, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 6. SECTOR-RELATIVE EBIT YIELD -- deviation from sector mean
    {
        "name": "r26_ebit_sector_relative",
        "expression": (
            "subtract(group_rank(ts_mean(divide(ebit, cap), 120), subindustry),"
            " group_mean(group_rank(ts_mean(divide(ebit, cap), 120), subindustry),"
            " 1, sector))"
        ),
        "settings": base_settings(decay=8, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
]


# =====================================================================
# Round 27: compose R26's new-structure signals into PASS alphas.
# All ingredients are ts_corr / sector-rel / divide / sign-gated --
# zero overlap with the rev3-based akNvjWRR family.
# =====================================================================
RV_CORR_FADE       = "-group_rank(ts_corr(returns, volume, 22), subindustry)"
CLOSE_VWAP_CORR_FLIP = "-group_rank(ts_corr(close, vwap, 22), subindustry)"
EBIT_SECTOR_REL    = (
    "subtract(group_rank(ts_mean(divide(ebit, cap), 120), subindustry),"
    " group_mean(group_rank(ts_mean(divide(ebit, cap), 120), subindustry),"
    " 1, sector))"
)
RATIO_FLIP = (
    "-divide(group_rank(ts_sum(returns, 22), subindustry),"
    " group_rank(ts_std_dev(returns, 60), subindustry))"
)

ROUND_27 = [
    # 1. 3-axis new-structure: sector-rel-EBIT + R-V corr fade + close-vwap corr flip
    {
        "name": "r27_3axis_new_struct_d6",
        "expression": (
            f"add(add({EBIT_SECTOR_REL}, {RV_CORR_FADE}), {CLOSE_VWAP_CORR_FLIP})"
        ),
        "settings": base_settings(decay=6, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 2. 4-axis: + ratio flip
    {
        "name": "r27_4axis_new_struct_d6",
        "expression": (
            f"add(add(add({EBIT_SECTOR_REL}, {RV_CORR_FADE}),"
            f" {CLOSE_VWAP_CORR_FLIP}), {RATIO_FLIP})"
        ),
        "settings": base_settings(decay=6, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 3. 5-axis: + 3 model-flips (mix new structure with model-flips,
    #    no add-rank stack family at all)
    {
        "name": "r27_5axis_struct_plus_3flips_d6",
        "expression": (
            f"add(add(add({EBIT_SECTOR_REL}, {RV_CORR_FADE}),"
            f" {CLOSE_VWAP_CORR_FLIP}), {SLOW_3FLIPS})"
        ),
        "settings": base_settings(decay=6, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 4. multiply interaction: sector-rel-EBIT x close-vwap-corr-flip
    #    (different combinator, not add)
    {
        "name": "r27_multiply_interaction_d6",
        "expression": (
            f"multiply({EBIT_SECTOR_REL}, {CLOSE_VWAP_CORR_FLIP})"
        ),
        "settings": base_settings(decay=6, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 5. d=4 push of R27#3 (the most likely PASS candidate)
    {
        "name": "r27_5axis_struct_plus_3flips_d4",
        "expression": (
            f"add(add(add({EBIT_SECTOR_REL}, {RV_CORR_FADE}),"
            f" {CLOSE_VWAP_CORR_FLIP}), {SLOW_3FLIPS})"
        ),
        "settings": base_settings(decay=4, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 6. 6-axis: + close-z (the R25 winning fast signal) +IV-skew
    {
        "name": "r27_6axis_super_struct_d6",
        "expression": (
            f"add(add(add(add({EBIT_SECTOR_REL}, {RV_CORR_FADE}),"
            f" {CLOSE_VWAP_CORR_FLIP}), {FAST_CLOSE_Z}), {SLOW_3FLIPS})"
        ),
        "settings": base_settings(decay=6, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
]


# =====================================================================
# Round 28: truly novel external transforms + new value axes.
# Tests structurally different wrappers and untested fields.
# =====================================================================
PRICE_TO_SALES = (
    "-group_rank(divide(cap, sales), subindustry)"
)
PRICE_TO_BOOK = (
    "-group_rank(divide(cap, equity), subindustry)"
)
R25_BASE = (
    f"add(add({FAST_CLOSE_Z}, {SLOW_3FLIPS}), {IV_SKEW})"
)

ROUND_28 = [
    # 1. ts_decay_linear wrap on R25 winner (different smoothing structure)
    {
        "name": "r28_ts_decay_wrap_d6",
        "expression": f"ts_decay_linear({R25_BASE}, 10)",
        "settings": base_settings(decay=6, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 2. quantile wrap (project to gaussian distribution)
    {
        "name": "r28_quantile_wrap_d6",
        "expression": f"quantile({R25_BASE})",
        "settings": base_settings(decay=6, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 3. R25 base + price-to-sales (new value axis: -cap/sales)
    {
        "name": "r28_r25_plus_ps_d6",
        "expression": f"add({R25_BASE}, {PRICE_TO_SALES})",
        "settings": base_settings(decay=6, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 4. R25 base + price-to-book (new value axis: -cap/equity)
    {
        "name": "r28_r25_plus_pb_d6",
        "expression": f"add({R25_BASE}, {PRICE_TO_BOOK})",
        "settings": base_settings(decay=6, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 5. R25 base + both P/S + P/B (mega-value augmentation)
    {
        "name": "r28_r25_plus_ps_pb_d4",
        "expression": (
            f"add(add({R25_BASE}, {PRICE_TO_SALES}), {PRICE_TO_BOOK})"
        ),
        "settings": base_settings(decay=4, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 6. R25 base + sector-rel EBIT (R26#6) at d=4
    {
        "name": "r28_r25_plus_sector_ebit_d4",
        "expression": f"add({R25_BASE}, {EBIT_SECTOR_REL})",
        "settings": base_settings(decay=4, neutralization="INDUSTRY",
                                  truncation=0.10, universe="TOP3000",
                                  pasteurization="OFF"),
    },
]


# =====================================================================
# Round 29: OBSCURE-FIELDS round. Every base field has userCount=0 on
# the WQ data catalog (TOP3000, delay=1, USA), i.e. zero alphas have
# been published using them on the platform. Goal: low correlation
# vs. the dense factor zoo + our prior 28 rounds.
#
# Axis selection rationale:
#   - IV mean-skew 180d (option/IV-surface)           : option-flow positioning
#   - days_to_cover (short-interest pressure)         : short-side crowding
#   - monchgsip (monthly change in short interest)    : flow of bear conviction
#   - industry_relative_fcf_to_price (industry-rel)   : pure value, pre-neutralized
#   - fcf_yield * forward_roe (composite Q*V)         : quality-tilted value
#   - inventory_change / avg_assets (accruals)        : earnings-quality anti-momentum
#
# Signs:
#   high IV skew (call rich)        -> reverse  (negative)
#   high days_to_cover              -> reverse  (negative — short crowded)
#   high monthly SI change          -> reverse  (negative — bears piling in)
#   high industry-rel FCF/P         -> long     (positive — value)
#   high FCF * fwd_ROE              -> long     (positive — quality value)
#   high inventory build            -> reverse  (negative — accrual junk)
# =====================================================================
IV_SKEW_OBS  = "-group_rank(ts_mean(implied_volatility_mean_skew_180, 22), subindustry)"
DTC_OBS      = "-group_rank(ts_mean(mdl77_shortsentimentfactor_days_to_cover, 22), subindustry)"
SI_CHG_OBS   = "-group_rank(ts_mean(mdl77_2liquidityriskfactor_monchgsip, 22), subindustry)"
FCF_REL_OBS  = "group_rank(ts_mean(industry_relative_fcf_to_price, 22), subindustry)"
FCFXROE_OBS  = "group_rank(ts_mean(fcf_yield_multiplied_forward_roe, 22), subindustry)"
INV_ACCR_OBS = "-group_rank(ts_mean(inventory_change_avg_assets, 22), subindustry)"

ROUND_29 = [
    # 1. IV skew 180d — option positioning premium reversal
    {
        "name": "r29_iv_skew_180",
        "expression": IV_SKEW_OBS,
        "settings": base_settings(decay=4, neutralization="SUBINDUSTRY",
                                  truncation=0.08, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 2. Days-to-cover — short-side crowding reversal
    {
        "name": "r29_days_to_cover",
        "expression": DTC_OBS,
        "settings": base_settings(decay=4, neutralization="SUBINDUSTRY",
                                  truncation=0.08, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 3. Monthly SI change — bear flow proxy reversal
    {
        "name": "r29_monthly_si_change",
        "expression": SI_CHG_OBS,
        "settings": base_settings(decay=4, neutralization="SUBINDUSTRY",
                                  truncation=0.08, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 4. Industry-rel FCF / P — pre-industry-normalized value
    {
        "name": "r29_fcf_industry_rel",
        "expression": FCF_REL_OBS,
        "settings": base_settings(decay=4, neutralization="SUBINDUSTRY",
                                  truncation=0.08, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 5. FCF yield * forward ROE — quality-tilted value
    {
        "name": "r29_fcf_x_roe",
        "expression": FCFXROE_OBS,
        "settings": base_settings(decay=4, neutralization="SUBINDUSTRY",
                                  truncation=0.08, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 6. Inventory change / avg assets — accrual anti-momentum
    {
        "name": "r29_inventory_accrual",
        "expression": INV_ACCR_OBS,
        "settings": base_settings(decay=4, neutralization="SUBINDUSTRY",
                                  truncation=0.08, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 7. Tri-axis composite: IV skew + days_to_cover + industry-rel FCF
    #    (option-flow + short-pressure + pure-value — three different
    #    mechanics, all using zero-userCount fields)
    {
        "name": "r29_triple_obscure",
        "expression": f"add(add({IV_SKEW_OBS}, {DTC_OBS}), {FCF_REL_OBS})",
        "settings": base_settings(decay=4, neutralization="SUBINDUSTRY",
                                  truncation=0.08, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 8. Quad composite: above + inventory accrual (adds quality axis)
    {
        "name": "r29_quad_obscure",
        "expression": (
            f"add(add(add({IV_SKEW_OBS}, {DTC_OBS}), {FCF_REL_OBS}), "
            f"{INV_ACCR_OBS})"
        ),
        "settings": base_settings(decay=4, neutralization="SUBINDUSTRY",
                                  truncation=0.08, universe="TOP3000",
                                  pasteurization="OFF"),
    },
]


# =====================================================================
# Round 30: sign-corrected obscure stacks. R29 calibration revealed
# IV_skew_180 wants raw sign (+), industry_rel_FCF/P wants negative
# sign in this regime (value penalty 2019-2023). The 5 surviving
# obscure axes (each userCount=0) become:
#   +group_rank(ts_mean(implied_volatility_mean_skew_180, 22), subindustry)
#   -group_rank(ts_mean(mdl77_shortsentimentfactor_days_to_cover, 22), subindustry)
#   -group_rank(ts_mean(mdl77_2liquidityriskfactor_monchgsip, 22), subindustry)
#   -group_rank(ts_mean(industry_relative_fcf_to_price, 22), subindustry)
#   -group_rank(ts_mean(inventory_change_avg_assets, 22), subindustry)
# =====================================================================
IV_SKEW_OBS2  =  "group_rank(ts_mean(implied_volatility_mean_skew_180, 22), subindustry)"
FCF_REL_OBS2  = "-group_rank(ts_mean(industry_relative_fcf_to_price, 22), subindustry)"

# Quad obscure (4 best uncorrelated axes, all corrected):
OBS_QUAD = (
    f"add(add(add({IV_SKEW_OBS2}, {SI_CHG_OBS}), {FCF_REL_OBS2}), {DTC_OBS})"
)
# Penta obscure (adds inventory-accrual quality):
OBS_PENTA = (
    f"add(add(add(add({IV_SKEW_OBS2}, {SI_CHG_OBS}), {FCF_REL_OBS2}), "
    f"{DTC_OBS}), {INV_ACCR_OBS})"
)

ROUND_30 = [
    # 1. IV skew 180 sign-flipped (verify standalone)
    {
        "name": "r30_iv_skew_180_pos",
        "expression": IV_SKEW_OBS2,
        "settings": base_settings(decay=4, neutralization="SUBINDUSTRY",
                                  truncation=0.08, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 2. industry-rel FCF/P sign-flipped (verify standalone)
    {
        "name": "r30_fcf_industry_rel_neg",
        "expression": FCF_REL_OBS2,
        "settings": base_settings(decay=4, neutralization="SUBINDUSTRY",
                                  truncation=0.08, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 3. Quad obscure stack (corrected)
    {
        "name": "r30_quad_obscure_v2",
        "expression": OBS_QUAD,
        "settings": base_settings(decay=4, neutralization="SUBINDUSTRY",
                                  truncation=0.08, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 4. Penta obscure stack (corrected, 5 axes)
    {
        "name": "r30_penta_obscure_v2",
        "expression": OBS_PENTA,
        "settings": base_settings(decay=4, neutralization="SUBINDUSTRY",
                                  truncation=0.08, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 5. Penta obscure + R25 base (R25 PASSed at SH=1.75; obscure axes
    #    add orthogonal lift). Hypothesis: WQ_SH > 2.0 with TO < 0.20.
    {
        "name": "r30_penta_obscure_plus_r25",
        "expression": f"add({OBS_PENTA}, {R25_BASE})",
        "settings": base_settings(decay=4, neutralization="INDUSTRY",
                                  truncation=0.08, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 6. Triple-best (IV_skew + SI_chg + FCF_rel — strongest 3) + R25
    {
        "name": "r30_tri_best_plus_r25",
        "expression": (
            f"add(add(add({IV_SKEW_OBS2}, {SI_CHG_OBS}), {FCF_REL_OBS2}), "
            f"{R25_BASE})"
        ),
        "settings": base_settings(decay=4, neutralization="INDUSTRY",
                                  truncation=0.08, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 7. Penta obscure decay=8 (smoother)
    {
        "name": "r30_penta_obscure_v2_d8",
        "expression": OBS_PENTA,
        "settings": base_settings(decay=8, neutralization="SUBINDUSTRY",
                                  truncation=0.08, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 8. Penta obscure + R25 base with quantile() wrap (R28#2 was a
    #    PASS with quantile() wrap — same trick on the new bigger stack)
    {
        "name": "r30_quantile_penta_plus_r25",
        "expression": f"quantile(add({OBS_PENTA}, {R25_BASE}))",
        "settings": base_settings(decay=4, neutralization="INDUSTRY",
                                  truncation=0.08, universe="TOP3000",
                                  pasteurization="OFF"),
    },
]


# =====================================================================
# Round 31: truly-orthogonal obscure axes + R25 anchor. R30 showed
# IV_skew_180 and model-77 short-interest fields partially duplicate
# R25_BASE (which already has IV_C270/P270 and model-177 axes), so
# stacking diluted rather than added. R31 restricts new axes to the
# ones with NO twin in R25:
#   - inventory_change_avg_assets   (accruals — R25 has no accrual)
#   - mdl77_shortsentimentfactor_days_to_cover (short-pressure — R25 no SI)
#   - industry_relative_fcf_to_price  (industry-rel FCF — R25 no FCF/P)
# Each is a userCount=0 obscure field on the WQ data catalog.
# =====================================================================
ROUND_31 = [
    # 1. R25 + INV_ACCR only (1 truly-new axis)
    {
        "name": "r31_r25_plus_inv_accr",
        "expression": f"add({R25_BASE}, {INV_ACCR_OBS})",
        "settings": base_settings(decay=4, neutralization="INDUSTRY",
                                  truncation=0.08, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 2. R25 + DTC only (1 truly-new axis)
    {
        "name": "r31_r25_plus_dtc",
        "expression": f"add({R25_BASE}, {DTC_OBS})",
        "settings": base_settings(decay=4, neutralization="INDUSTRY",
                                  truncation=0.08, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 3. R25 + FCF_REL (negative sign — flipped per R30 calibration)
    {
        "name": "r31_r25_plus_fcf_rel",
        "expression": f"add({R25_BASE}, {FCF_REL_OBS2})",
        "settings": base_settings(decay=4, neutralization="INDUSTRY",
                                  truncation=0.08, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 4. R25 + INV_ACCR + DTC (2 truly-orthogonal axes)
    {
        "name": "r31_r25_plus_inv_dtc",
        "expression": f"add(add({R25_BASE}, {INV_ACCR_OBS}), {DTC_OBS})",
        "settings": base_settings(decay=4, neutralization="INDUSTRY",
                                  truncation=0.08, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 5. R25 + 3 truly-orthogonal axes (INV_ACCR + DTC + FCF_REL)
    {
        "name": "r31_r25_plus_tri_ortho",
        "expression": (
            f"add(add(add({R25_BASE}, {INV_ACCR_OBS}), {DTC_OBS}), "
            f"{FCF_REL_OBS2})"
        ),
        "settings": base_settings(decay=4, neutralization="INDUSTRY",
                                  truncation=0.08, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 6. Same #5 with winsorize wrap (R21 trick — clip tail outliers)
    {
        "name": "r31_winsorize_tri_ortho_plus_r25",
        "expression": (
            f"winsorize(add(add(add({R25_BASE}, {INV_ACCR_OBS}), {DTC_OBS}), "
            f"{FCF_REL_OBS2}))"
        ),
        "settings": base_settings(decay=4, neutralization="INDUSTRY",
                                  truncation=0.08, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 7. Same #5 with zscore wrap (R21 trick — re-standardize)
    {
        "name": "r31_zscore_tri_ortho_plus_r25",
        "expression": (
            f"zscore(add(add(add({R25_BASE}, {INV_ACCR_OBS}), {DTC_OBS}), "
            f"{FCF_REL_OBS2}))"
        ),
        "settings": base_settings(decay=4, neutralization="INDUSTRY",
                                  truncation=0.08, universe="TOP3000",
                                  pasteurization="OFF"),
    },
    # 8. Same #5 with decay=5 (R18 winners often used d=5 for SH lift)
    {
        "name": "r31_r25_plus_tri_ortho_d5",
        "expression": (
            f"add(add(add({R25_BASE}, {INV_ACCR_OBS}), {DTC_OBS}), "
            f"{FCF_REL_OBS2})"
        ),
        "settings": base_settings(decay=5, neutralization="INDUSTRY",
                                  truncation=0.08, universe="TOP3000",
                                  pasteurization="OFF"),
    },
]


# =====================================================================
# Round 32: DELAY=0 calibration. The CLAUDE.md note "delay=0 not
# available" is STALE — a probe (alpha d5n79YEv) confirmed delay=0
# now simulates fine on this account. delay=0 exposes only
# fundamental / news / analyst / pv / option / socialmedia (NO model
# category), so R25_BASE and the R31 winners cannot run at D0.
# This round mines D0-native factors from scratch across the 4 alt-data
# families that are dense at delay=0:
#   - intraday news reaction  (news_*)        : reversal hypotheses
#   - option IV surface       (implied_volatility_*)
#   - supply-chain peer returns (rel_ret_*)   : lead-lag
#   - analyst forward estimates (est_*)       : forward value
# All base fields have low userCount on the WQ catalog.
# =====================================================================
D0_NEWS_5MIN   = "-group_rank(ts_mean(news_pct_5_min, 5), subindustry)"
D0_NEWS_MAXUP  = "-group_rank(ts_mean(news_max_up_ret, 5), subindustry)"
D0_NEWS_VOLRAT = "group_rank(ts_mean(news_ratio_vol, 5), subindustry)"
D0_NEWS_RANGE  = "-group_rank(ts_mean(news_range_stddev, 5), subindustry)"
D0_NEWS_PREVD  = "-group_rank(ts_mean(news_prev_day_ret, 5), subindustry)"
D0_NEWS_GAP    = "-group_rank(ts_mean(news_open_gap, 5), subindustry)"
D0_IV_SKEW180  = "group_rank(ts_mean(implied_volatility_mean_skew_180, 22), subindustry)"
D0_REL_COMP    = "group_rank(ts_mean(rel_ret_comp, 5), subindustry)"
D0_REL_PART    = "group_rank(ts_mean(rel_ret_part, 5), subindustry)"
D0_EST_EBIT    = "group_rank(ts_mean(divide(est_ebit, cap), 22), subindustry)"


def base_settings_d0(**overrides):
    d0 = dict(delay=0, decay=4, neutralization="INDUSTRY",
              truncation=0.08, universe="TOP3000", pasteurization="OFF")
    d0.update(overrides)
    return base_settings(**d0)


ROUND_32 = [
    {"name": "r32_d0_news_5min_rev",   "expression": D0_NEWS_5MIN,
     "settings": base_settings_d0()},
    {"name": "r32_d0_news_maxup_rev",  "expression": D0_NEWS_MAXUP,
     "settings": base_settings_d0()},
    {"name": "r32_d0_news_vol_ratio",  "expression": D0_NEWS_VOLRAT,
     "settings": base_settings_d0()},
    {"name": "r32_d0_news_range_z",    "expression": D0_NEWS_RANGE,
     "settings": base_settings_d0()},
    {"name": "r32_d0_news_prevday_rev","expression": D0_NEWS_PREVD,
     "settings": base_settings_d0()},
    {"name": "r32_d0_news_gap_rev",    "expression": D0_NEWS_GAP,
     "settings": base_settings_d0()},
    {"name": "r32_d0_iv_skew_180",     "expression": D0_IV_SKEW180,
     "settings": base_settings_d0()},
    {"name": "r32_d0_rel_ret_comp",    "expression": D0_REL_COMP,
     "settings": base_settings_d0()},
    {"name": "r32_d0_rel_ret_part",    "expression": D0_REL_PART,
     "settings": base_settings_d0()},
    {"name": "r32_d0_est_ebit_yield",  "expression": D0_EST_EBIT,
     "settings": base_settings_d0()},
]


# =====================================================================
# Round 33: delay=0 stacks toward the SH>=1.75 gate. R32 showed only
# two D0 axes have usable turnover: IV_skew_180 (SH 0.89, TO 0.078)
# and analyst-estimate value est_ebit/cap (SH 0.98, TO 0.018). All
# news_* / rel_ret_* fields churn at TO 0.37-0.49 and are unusable
# standalone. Strategy:
#   - stack the low-TO analyst-estimate value axes (est_fcf, est_ebitda,
#     est_netprofit, est_cashflow_op — all forward estimates, slow-moving)
#   - diversify with IV_skew_180 (option-flow, orthogonal to value)
#   - separately, tame the strong news_prevday_rev signal (SH 1.05 but
#     TO 0.41) with a long ts_mean window + heavy decay
# =====================================================================
D0_EST_FCF      = "group_rank(ts_mean(divide(est_fcf, cap), 22), subindustry)"
D0_EST_EBITDA   = "group_rank(ts_mean(divide(est_ebitda, cap), 22), subindustry)"
D0_EST_NETPROF  = "group_rank(ts_mean(divide(est_netprofit, cap), 22), subindustry)"
D0_EST_CFO      = "group_rank(ts_mean(divide(est_cashflow_op, cap), 22), subindustry)"
# news_prevday_rev tamed: 60d smoothing window (vs 5d in R32)
D0_NEWS_PREVD_SLOW = "-group_rank(ts_mean(news_prev_day_ret, 60), subindustry)"

# 5-axis low-TO D0 stack: option-flow + 4 forward-estimate value axes
D0_VALUE_OPT_5 = (
    f"add(add(add(add({D0_IV_SKEW180}, {D0_EST_EBIT}), {D0_EST_FCF}), "
    f"{D0_EST_EBITDA}), {D0_EST_CFO})"
)

ROUND_33 = [
    # 1-4: calibrate the new forward-estimate value axes standalone
    {"name": "r33_d0_est_fcf_yield",    "expression": D0_EST_FCF,
     "settings": base_settings_d0()},
    {"name": "r33_d0_est_ebitda_yield", "expression": D0_EST_EBITDA,
     "settings": base_settings_d0()},
    {"name": "r33_d0_est_netprof_yield","expression": D0_EST_NETPROF,
     "settings": base_settings_d0()},
    {"name": "r33_d0_est_cfo_yield",    "expression": D0_EST_CFO,
     "settings": base_settings_d0()},
    # 5: IV_skew + est_ebit (option + value, 2-axis)
    {"name": "r33_d0_iv_plus_ebit",
     "expression": f"add({D0_IV_SKEW180}, {D0_EST_EBIT})",
     "settings": base_settings_d0()},
    # 6: IV_skew + est_ebit + est_fcf (3-axis)
    {"name": "r33_d0_iv_ebit_fcf",
     "expression": f"add(add({D0_IV_SKEW180}, {D0_EST_EBIT}), {D0_EST_FCF})",
     "settings": base_settings_d0()},
    # 7: full 5-axis low-TO value+option stack
    {"name": "r33_d0_value_opt_5axis",
     "expression": D0_VALUE_OPT_5,
     "settings": base_settings_d0()},
    # 8: news_prevday_rev tamed (60d window + heavy decay)
    {"name": "r33_d0_news_prevday_slow",
     "expression": D0_NEWS_PREVD_SLOW,
     "settings": base_settings_d0(decay=32)},
    # 9: tamed news + IV_skew + est_ebit (mix strong news w/ low-TO anchors)
    {"name": "r33_d0_news_slow_plus_iv_ebit",
     "expression": (
         f"add(add({D0_NEWS_PREVD_SLOW}, {D0_IV_SKEW180}), {D0_EST_EBIT})"
     ),
     "settings": base_settings_d0(decay=16)},
    # 10: mega — 5-axis value+option + tamed news (6 axes)
    {"name": "r33_d0_mega_6axis",
     "expression": f"add({D0_VALUE_OPT_5}, {D0_NEWS_PREVD_SLOW})",
     "settings": base_settings_d0(decay=16)},
]


# =====================================================================
# Round 34: genuinely-orthogonal delay=0 axes. R33 hit a ~1.12 ceiling
# because every low-TO D0 signal was a collinear "forward earnings
# yield". R34 adds axes that are structurally different from value:
#   - estimate REVISION (ts_delta of est_*) — momentum of forecasts,
#     orthogonal to forecast LEVEL
#   - low-vol anomaly (parkinson_volatility) — risk axis
#   - IV term-structure level (implied_volatility_mean_720)
#   - social sentiment (scl12_sentiment, snt_buzz)
# Items 1-6 calibrate standalone; 7-10 stack the confident ones onto
# the best R33 base (tamed-news + IV + est_ebit, alpha QPnlpLeM).
# =====================================================================
D0_EST_EBIT_REV  = "group_rank(ts_delta(est_ebit, 60), subindustry)"
D0_EST_NP_REV    = "group_rank(ts_delta(est_netprofit, 60), subindustry)"
D0_PARKINSON_LV  = "-group_rank(ts_mean(parkinson_volatility_20, 22), subindustry)"
D0_IV_LEVEL_720  = "-group_rank(ts_mean(implied_volatility_mean_720, 22), subindustry)"
D0_SENTIMENT     = "group_rank(ts_mean(scl12_sentiment, 22), subindustry)"
D0_BUZZ          = "group_rank(ts_mean(snt_buzz, 22), subindustry)"

# Best R33 stack (tamed-news + IV + est_ebit) reused as the anchor:
D0_R33_BASE = (
    f"add(add({D0_NEWS_PREVD_SLOW}, {D0_IV_SKEW180}), {D0_EST_EBIT})"
)

ROUND_34 = [
    # 1-6: calibrate the new orthogonal axes standalone
    {"name": "r34_d0_est_ebit_revision",  "expression": D0_EST_EBIT_REV,
     "settings": base_settings_d0()},
    {"name": "r34_d0_est_np_revision",    "expression": D0_EST_NP_REV,
     "settings": base_settings_d0()},
    {"name": "r34_d0_parkinson_lowvol",   "expression": D0_PARKINSON_LV,
     "settings": base_settings_d0()},
    {"name": "r34_d0_iv_level_720",       "expression": D0_IV_LEVEL_720,
     "settings": base_settings_d0()},
    {"name": "r34_d0_sentiment",          "expression": D0_SENTIMENT,
     "settings": base_settings_d0()},
    {"name": "r34_d0_buzz",               "expression": D0_BUZZ,
     "settings": base_settings_d0()},
    # 7: R33 base + estimate-revision (value + revision momentum)
    {"name": "r34_d0_base_plus_revision",
     "expression": f"add({D0_R33_BASE}, {D0_EST_EBIT_REV})",
     "settings": base_settings_d0(decay=16)},
    # 8: R33 base + low-vol anomaly
    {"name": "r34_d0_base_plus_lowvol",
     "expression": f"add({D0_R33_BASE}, {D0_PARKINSON_LV})",
     "settings": base_settings_d0(decay=16)},
    # 9: R33 base + revision + low-vol (3 orthogonal axes added)
    {"name": "r34_d0_base_plus_rev_lowvol",
     "expression": (
         f"add(add({D0_R33_BASE}, {D0_EST_EBIT_REV}), {D0_PARKINSON_LV})"
     ),
     "settings": base_settings_d0(decay=16)},
    # 10: mega — R33 base + revision + low-vol + IV-level-720
    {"name": "r34_d0_mega_orthogonal",
     "expression": (
         f"add(add(add({D0_R33_BASE}, {D0_EST_EBIT_REV}), "
         f"{D0_PARKINSON_LV}), {D0_IV_LEVEL_720})"
     ),
     "settings": base_settings_d0(decay=16)},
]


# =====================================================================
# Round 35: delay=0 SETTINGS sweep on the best base. R32-R34 found the
# D0 expression ceiling at ~1.12 (QPnlpLeM = tamed-news + IV + est_ebit).
# The one Pareto lever not yet pulled at D0 is the settings axis
# (decay / neutralization / truncation / universe). Per prior-session
# notes the decay axis is the primary control and pasteurization=OFF
# lifts SH. Base = R33 best + buzz (the one confirmed orthogonal axis
# from R34, SH 0.40 TO 0.083).
# =====================================================================
D0_R35_BASE = f"add({D0_R33_BASE}, {D0_BUZZ})"

ROUND_35 = [
    {"name": "r35_d0_sweep_d4_ind",
     "expression": D0_R35_BASE, "settings": base_settings_d0(decay=4)},
    {"name": "r35_d0_sweep_d8_ind",
     "expression": D0_R35_BASE, "settings": base_settings_d0(decay=8)},
    {"name": "r35_d0_sweep_d16_ind",
     "expression": D0_R35_BASE, "settings": base_settings_d0(decay=16)},
    {"name": "r35_d0_sweep_d32_ind",
     "expression": D0_R35_BASE, "settings": base_settings_d0(decay=32)},
    {"name": "r35_d0_sweep_d8_subind",
     "expression": D0_R35_BASE,
     "settings": base_settings_d0(decay=8, neutralization="SUBINDUSTRY")},
    {"name": "r35_d0_sweep_d8_sector",
     "expression": D0_R35_BASE,
     "settings": base_settings_d0(decay=8, neutralization="SECTOR")},
    {"name": "r35_d0_sweep_d8_market",
     "expression": D0_R35_BASE,
     "settings": base_settings_d0(decay=8, neutralization="MARKET")},
    {"name": "r35_d0_sweep_d8_t005",
     "expression": D0_R35_BASE,
     "settings": base_settings_d0(decay=8, truncation=0.05)},
    {"name": "r35_d0_sweep_d8_t010",
     "expression": D0_R35_BASE,
     "settings": base_settings_d0(decay=8, truncation=0.10)},
    {"name": "r35_d0_sweep_d8_top1000",
     "expression": D0_R35_BASE,
     "settings": base_settings_d0(decay=8, universe="TOP1000")},
    {"name": "r35_d0_sweep_d8_top500",
     "expression": D0_R35_BASE,
     "settings": base_settings_d0(decay=8, universe="TOP500")},
    {"name": "r35_d0_sweep_d16_subind_t005",
     "expression": D0_R35_BASE,
     "settings": base_settings_d0(decay=16, neutralization="SUBINDUSTRY",
                                  truncation=0.05)},
]


# =====================================================================
# Round 36: delay=0 QUALITY/PROFITABILITY axes. R32-R35 hit a ~1.12
# ceiling because every low-TO D0 signal was a collinear "earnings
# yield" (est_X / cap). R36 builds RATIOS of estimate fields that are
# structurally orthogonal to earnings-yield:
#   - forward ROA          est_ebit / est_tot_assets   (profitability)
#   - gross profitability  est_grossincome / est_tot_assets (Novy-Marx)
#   - investment/capex     est_capex / est_tot_assets   (asset growth)
#   - leverage             est_netdebt / est_shequity
#   - book-to-market       est_bookvalue_ps / close
#   - SGA efficiency       est_sga / est_grossincome
#   - cash conversion      est_cashflow_op / est_ebit   (earnings quality)
#   - goodwill burden      est_tot_goodwill / est_tot_assets
# Items 1-8 calibrate standalone; 9-10 stack the quality axes onto the
# best R33 base (tamed-news + IV + est_ebit).
# =====================================================================
D0_FWD_ROA    = "group_rank(divide(est_ebit, est_tot_assets), subindustry)"
D0_GROSS_PROF = "group_rank(divide(est_grossincome, est_tot_assets), subindustry)"
D0_INVEST     = "-group_rank(divide(est_capex, est_tot_assets), subindustry)"
D0_LEVERAGE   = "-group_rank(divide(est_netdebt, est_shequity), subindustry)"
D0_BOOK_MKT   = "group_rank(divide(est_bookvalue_ps, close), subindustry)"
D0_SGA_EFF    = "-group_rank(divide(est_sga, est_grossincome), subindustry)"
D0_CASH_CONV  = "group_rank(divide(est_cashflow_op, est_ebit), subindustry)"
D0_GOODWILL   = "-group_rank(divide(est_tot_goodwill, est_tot_assets), subindustry)"

ROUND_36 = [
    {"name": "r36_d0_fwd_roa",       "expression": D0_FWD_ROA,
     "settings": base_settings_d0()},
    {"name": "r36_d0_gross_prof",    "expression": D0_GROSS_PROF,
     "settings": base_settings_d0()},
    {"name": "r36_d0_investment",    "expression": D0_INVEST,
     "settings": base_settings_d0()},
    {"name": "r36_d0_leverage",      "expression": D0_LEVERAGE,
     "settings": base_settings_d0()},
    {"name": "r36_d0_book_market",   "expression": D0_BOOK_MKT,
     "settings": base_settings_d0()},
    {"name": "r36_d0_sga_efficiency","expression": D0_SGA_EFF,
     "settings": base_settings_d0()},
    {"name": "r36_d0_cash_conversion","expression": D0_CASH_CONV,
     "settings": base_settings_d0()},
    {"name": "r36_d0_goodwill_burden","expression": D0_GOODWILL,
     "settings": base_settings_d0()},
    # 9: R33 base + forward ROA + gross profitability (quality stack)
    {"name": "r36_d0_base_plus_quality",
     "expression": f"add(add({D0_R33_BASE}, {D0_FWD_ROA}), {D0_GROSS_PROF})",
     "settings": base_settings_d0(decay=16)},
    # 10: R33 base + ROA + gross prof + book-to-market (quality + value)
    {"name": "r36_d0_base_plus_quality_bm",
     "expression": (
         f"add(add(add({D0_R33_BASE}, {D0_FWD_ROA}), {D0_GROSS_PROF}), "
         f"{D0_BOOK_MKT})"
     ),
     "settings": base_settings_d0(decay=16)},
]


# =====================================================================
# Round 37: delay=0 stacks with the 3 R36-confirmed orthogonal axes.
# R36 found investment/capex (SH 0.87), leverage-FLIPPED (SH 0.73) and
# book-to-market (SH 0.72) all work standalone with tiny TO. R37 stacks
# them onto the R33 base (tamed-news + IV + est_ebit, SH 1.12) to push
# past the SH>1.5 gate. Leverage sign is flipped vs R36 (high leverage
# was bullish 2019-23).
# =====================================================================
D0_LEVERAGE_POS = "group_rank(divide(est_netdebt, est_shequity), subindustry)"
# 3-axis quality/value block (all R36 winners):
D0_QV3 = f"add(add({D0_INVEST}, {D0_LEVERAGE_POS}), {D0_BOOK_MKT})"
# full stack: R33 base + 3-axis quality/value
D0_FULL6 = f"add({D0_R33_BASE}, {D0_QV3})"

ROUND_37 = [
    {"name": "r37_d0_base_plus_invest",
     "expression": f"add({D0_R33_BASE}, {D0_INVEST})",
     "settings": base_settings_d0(decay=8)},
    {"name": "r37_d0_base_plus_leverage",
     "expression": f"add({D0_R33_BASE}, {D0_LEVERAGE_POS})",
     "settings": base_settings_d0(decay=8)},
    {"name": "r37_d0_base_plus_bookmkt",
     "expression": f"add({D0_R33_BASE}, {D0_BOOK_MKT})",
     "settings": base_settings_d0(decay=8)},
    {"name": "r37_d0_base_plus_invest_leverage",
     "expression": f"add(add({D0_R33_BASE}, {D0_INVEST}), {D0_LEVERAGE_POS})",
     "settings": base_settings_d0(decay=8)},
    {"name": "r37_d0_full6_d4",
     "expression": D0_FULL6, "settings": base_settings_d0(decay=4)},
    {"name": "r37_d0_full6_d8",
     "expression": D0_FULL6, "settings": base_settings_d0(decay=8)},
    {"name": "r37_d0_full6_d16",
     "expression": D0_FULL6, "settings": base_settings_d0(decay=16)},
    {"name": "r37_d0_full6_market",
     "expression": D0_FULL6,
     "settings": base_settings_d0(decay=8, neutralization="MARKET")},
    {"name": "r37_d0_full6_sector",
     "expression": D0_FULL6,
     "settings": base_settings_d0(decay=8, neutralization="SECTOR")},
    {"name": "r37_d0_qv3_standalone",
     "expression": D0_QV3, "settings": base_settings_d0(decay=8)},
    {"name": "r37_d0_full6_winsorize",
     "expression": f"winsorize({D0_FULL6})",
     "settings": base_settings_d0(decay=8)},
    # est_ebit may overlap book-to-market (both value); test base w/o it:
    {"name": "r37_d0_news_iv_plus_qv3",
     "expression": (
         f"add(add(add(-group_rank(ts_mean(news_prev_day_ret, 60), subindustry), "
         f"{D0_IV_SKEW180}), {D0_QV3}), {D0_EST_EBIT})"
     ),
     "settings": base_settings_d0(decay=8, neutralization="MARKET")},
]


# =====================================================================
# Round 38: delay=0 GENUINELY-NEW axes. R32-R37 (64 sims) showed value
# and quality D0 fields are all cross-correlated. R38 reaches for
# mechanically-different signals not yet tried at D0:
#   - news_short_interest      : short-side crowding (D0 analog of the
#                                days_to_cover that powered R31's PASS)
#   - variance risk premium    : IV_mean_180 - HV_180 (option richness)
#   - IV term-structure slope  : skew_30 - skew_360
#   - news P/E ratio           : reported earnings multiple (value)
#   - news dividend yield      : income/value
#   - news result-vs-index     : post-news return vs SPY (reversal)
#   - historical-vol low-vol   : close-to-close vol (vs parkinson, R34)
# Items 1-8 calibrate standalone; 9-10 stack onto the R33 base.
# =====================================================================
D0_NEWS_SI    = "-group_rank(ts_mean(news_short_interest, 22), subindustry)"
D0_NWS_SI     = "-group_rank(ts_mean(nws12_mainz_short_interest, 22), subindustry)"
D0_VRP        = ("group_rank(ts_mean(subtract(implied_volatility_mean_180, "
                 "historical_volatility_180), 22), subindustry)")
D0_IV_TS_SLOPE = ("group_rank(ts_mean(subtract(implied_volatility_mean_skew_30, "
                  "implied_volatility_mean_skew_360), 22), subindustry)")
D0_NEWS_PE    = "-group_rank(ts_mean(news_pe_ratio, 22), subindustry)"
D0_DIV_YIELD  = "group_rank(ts_mean(news_dividend_yield, 22), subindustry)"
D0_RES_VS_IDX = "-group_rank(ts_mean(nws12_mainz_result_vs_index, 5), subindustry)"
D0_HV_LOWVOL  = "-group_rank(ts_mean(historical_volatility_60, 22), subindustry)"

ROUND_38 = [
    {"name": "r38_d0_news_short_interest", "expression": D0_NEWS_SI,
     "settings": base_settings_d0()},
    {"name": "r38_d0_nws_short_interest",  "expression": D0_NWS_SI,
     "settings": base_settings_d0()},
    {"name": "r38_d0_variance_risk_prem",  "expression": D0_VRP,
     "settings": base_settings_d0()},
    {"name": "r38_d0_iv_term_slope",       "expression": D0_IV_TS_SLOPE,
     "settings": base_settings_d0()},
    {"name": "r38_d0_news_pe_ratio",       "expression": D0_NEWS_PE,
     "settings": base_settings_d0()},
    {"name": "r38_d0_dividend_yield",      "expression": D0_DIV_YIELD,
     "settings": base_settings_d0()},
    {"name": "r38_d0_result_vs_index",     "expression": D0_RES_VS_IDX,
     "settings": base_settings_d0()},
    {"name": "r38_d0_hist_lowvol",         "expression": D0_HV_LOWVOL,
     "settings": base_settings_d0()},
    # 9: R33 base + news short interest (best-guess strongest new axis)
    {"name": "r38_d0_base_plus_news_si",
     "expression": f"add({D0_R33_BASE}, {D0_NEWS_SI})",
     "settings": base_settings_d0(decay=8)},
    # 10: R33 base + news short interest + VRP
    {"name": "r38_d0_base_plus_si_vrp",
     "expression": f"add(add({D0_R33_BASE}, {D0_NEWS_SI}), {D0_VRP})",
     "settings": base_settings_d0(decay=8)},
]


# =====================================================================
# Round 39: delay=0 stacks of the R38 winners with CORRECTED signs.
# R38 confirmed news_pe_ratio (0.83), news_short_interest-flipped
# (0.77) and iv_term_slope (0.67) all work standalone. R39 stacks them
# (correct signs) plus selective best axes from earlier D0 rounds.
# This is the final D0 attempt at the SH>1.5 gate.
# =====================================================================
D0_NEWS_SI_POS = "group_rank(ts_mean(news_short_interest, 22), subindustry)"

ROUND_39 = [
    # 1: 2 strongest R38 axes
    {"name": "r39_d0_pe_plus_si",
     "expression": f"add({D0_NEWS_PE}, {D0_NEWS_SI_POS})",
     "settings": base_settings_d0(decay=8)},
    # 2: 3 R38 axes
    {"name": "r39_d0_pe_si_slope",
     "expression": f"add(add({D0_NEWS_PE}, {D0_NEWS_SI_POS}), {D0_IV_TS_SLOPE})",
     "settings": base_settings_d0(decay=8)},
    # 3: news_pe + est_ebit (best value pair)
    {"name": "r39_d0_pe_plus_ebit",
     "expression": f"add({D0_NEWS_PE}, {D0_EST_EBIT})",
     "settings": base_settings_d0(decay=8)},
    # 4: news_pe + IV skew (value + option-flow)
    {"name": "r39_d0_pe_plus_ivskew",
     "expression": f"add({D0_NEWS_PE}, {D0_IV_SKEW180})",
     "settings": base_settings_d0(decay=8)},
    # 5: news_pe + news_si + IV skew
    {"name": "r39_d0_pe_si_ivskew",
     "expression": f"add(add({D0_NEWS_PE}, {D0_NEWS_SI_POS}), {D0_IV_SKEW180})",
     "settings": base_settings_d0(decay=8)},
    # 6: 5-axis kitchen sink (pe + si + slope + ebit + ivskew)
    {"name": "r39_d0_5axis_sink",
     "expression": (
         f"add(add(add(add({D0_NEWS_PE}, {D0_NEWS_SI_POS}), "
         f"{D0_IV_TS_SLOPE}), {D0_EST_EBIT}), {D0_IV_SKEW180})"
     ),
     "settings": base_settings_d0(decay=8)},
    # 7: 5-axis sink at decay=4
    {"name": "r39_d0_5axis_sink_d4",
     "expression": (
         f"add(add(add(add({D0_NEWS_PE}, {D0_NEWS_SI_POS}), "
         f"{D0_IV_TS_SLOPE}), {D0_EST_EBIT}), {D0_IV_SKEW180})"
     ),
     "settings": base_settings_d0(decay=4)},
    # 8: 5-axis sink at MARKET neutralization
    {"name": "r39_d0_5axis_sink_market",
     "expression": (
         f"add(add(add(add({D0_NEWS_PE}, {D0_NEWS_SI_POS}), "
         f"{D0_IV_TS_SLOPE}), {D0_EST_EBIT}), {D0_IV_SKEW180})"
     ),
     "settings": base_settings_d0(decay=8, neutralization="MARKET")},
    # 9: news_pe + investment (R36 axis)
    {"name": "r39_d0_pe_plus_invest",
     "expression": f"add({D0_NEWS_PE}, {D0_INVEST})",
     "settings": base_settings_d0(decay=8)},
    # 10: news_pe + news_si + investment + book-to-market
    {"name": "r39_d0_pe_si_invest_bm",
     "expression": (
         f"add(add(add({D0_NEWS_PE}, {D0_NEWS_SI_POS}), {D0_INVEST}), "
         f"{D0_BOOK_MKT})"
     ),
     "settings": base_settings_d0(decay=8)},
]


# =====================================================================
# Round 40: harden MPbKGgxr to pass the FULL WQ check set.
# MPbKGgxr (R39#8) cleared SH>1.5 but failed WQ's submittable gate:
#   - Sharpe 1.52 < 2.0 cutoff
#   - Weight concentration 16.67% > 10% (on 2021-05-05)
#   - Sub-universe Sharpe 0.60 < 0.66
# R40 attacks all three by:
#   - tightening truncation 0.08 -> 0.05/0.03  (concentration fix)
#   - adding 6th/7th orthogonal axes (push SH + sub-universe robust)
#   - winsorize wrap (clip outlier weights -> concentration)
# Base expression is MPbKGgxr's 5-axis: pe + si + iv_ts + ebit + ivskew
# =====================================================================
D0_BASE5_PASS = (
    f"add(add(add(add({D0_NEWS_PE}, {D0_NEWS_SI_POS}), {D0_IV_TS_SLOPE}), "
    f"{D0_EST_EBIT}), {D0_IV_SKEW180})"
)

ROUND_40 = [
    # 1: base + truncation=0.05 (concentration fix)
    {"name": "r40_d0_base5_t005",
     "expression": D0_BASE5_PASS,
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
    # 2: base + truncation=0.03 (very tight cap)
    {"name": "r40_d0_base5_t003",
     "expression": D0_BASE5_PASS,
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.03)},
    # 3: base + SUBINDUSTRY neut (sub-universe robustness)
    {"name": "r40_d0_base5_subind_t005",
     "expression": D0_BASE5_PASS,
     "settings": base_settings_d0(decay=8, neutralization="SUBINDUSTRY",
                                  truncation=0.05)},
    # 4: 6-axis: base + investment (R36 strongest standalone 0.87)
    {"name": "r40_d0_base5_plus_invest_t005",
     "expression": f"add({D0_BASE5_PASS}, {D0_INVEST})",
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
    # 5: 6-axis: base + leverage_pos
    {"name": "r40_d0_base5_plus_leverage_t005",
     "expression": f"add({D0_BASE5_PASS}, {D0_LEVERAGE_POS})",
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
    # 6: 6-axis: base + book-to-market
    {"name": "r40_d0_base5_plus_bm_t005",
     "expression": f"add({D0_BASE5_PASS}, {D0_BOOK_MKT})",
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
    # 7: 7-axis: base + investment + leverage_pos
    {"name": "r40_d0_base5_plus_invest_lev_t005",
     "expression": (
         f"add(add({D0_BASE5_PASS}, {D0_INVEST}), {D0_LEVERAGE_POS})"
     ),
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
    # 8: base + winsorize wrap (clip outlier weights)
    {"name": "r40_d0_base5_winsorize",
     "expression": f"winsorize({D0_BASE5_PASS})",
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.08)},
    # 9: base + winsorize + trunc=0.05 (combine fixes)
    {"name": "r40_d0_base5_winsorize_t005",
     "expression": f"winsorize({D0_BASE5_PASS})",
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
    # 10: 6-axis + winsorize + trunc=0.05 (max safety)
    {"name": "r40_d0_6axis_invest_winsorize_t005",
     "expression": f"winsorize(add({D0_BASE5_PASS}, {D0_INVEST}))",
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
]


# =====================================================================
# Round 41: target CONCENTRATED_WEIGHT and SUB_UNIVERSE_SHARPE checks.
# R40 showed truncation 0.05/0.03 leaves concentration at 0.167 (=1/6),
# so truncation is NOT the lever. Hypothesis: rank-bucketing or sector
# concentration. R41 tries: pasteurization=ON, higher decay (smoothing),
# outer wraps (zscore/normalize), continuous (ts_zscore) vs group_rank,
# stripped 3-axis and 2-axis variants (less rank ties).
# User accepts SH>=1.5; goal is CONCENTRATED_WEIGHT<=0.1 AND
# SUB_UNIVERSE_SHARPE>=0.66.
# =====================================================================
ROUND_41 = [
    # 1: base5 + pasteurization=ON (smooth signal)
    {"name": "r41_d0_base5_pasteur_on",
     "expression": D0_BASE5_PASS,
     "settings": dict(base_settings_d0(decay=8, neutralization="MARKET",
                                       truncation=0.05),
                      pasteurization="ON")},
    # 2: base5 + decay=16 (heavier smoothing)
    {"name": "r41_d0_base5_decay16",
     "expression": D0_BASE5_PASS,
     "settings": base_settings_d0(decay=16, neutralization="MARKET",
                                  truncation=0.05)},
    # 3: base5 + decay=32 (very heavy smoothing)
    {"name": "r41_d0_base5_decay32",
     "expression": D0_BASE5_PASS,
     "settings": base_settings_d0(decay=32, neutralization="MARKET",
                                  truncation=0.05)},
    # 4: zscore-wrap base5 (continuous redistribution)
    {"name": "r41_d0_zscore_wrap",
     "expression": f"zscore({D0_BASE5_PASS})",
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
    # 5: normalize wrap (L1-norm redistribute)
    {"name": "r41_d0_normalize_wrap",
     "expression": f"normalize({D0_BASE5_PASS})",
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
    # 6: scale wrap (1-norm)
    {"name": "r41_d0_scale_wrap",
     "expression": f"scale({D0_BASE5_PASS})",
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
    # 7: 3-axis only (pe + si + ivskew, R39's strong combo) - simpler signal
    {"name": "r41_d0_3axis_d16",
     "expression": (
         f"add(add({D0_NEWS_PE}, {D0_NEWS_SI_POS}), {D0_IV_SKEW180})"
     ),
     "settings": base_settings_d0(decay=16, neutralization="MARKET",
                                  truncation=0.05)},
    # 8: 2-axis pe + si only (simplest) + decay=16
    {"name": "r41_d0_2axis_pe_si_d16",
     "expression": f"add({D0_NEWS_PE}, {D0_NEWS_SI_POS})",
     "settings": base_settings_d0(decay=16, neutralization="MARKET",
                                  truncation=0.05)},
    # 9: base5 SUBINDUSTRY neut + decay=16 + zscore wrap (max smoothing+redistribution)
    {"name": "r41_d0_zscore_subind_d16",
     "expression": f"zscore({D0_BASE5_PASS})",
     "settings": base_settings_d0(decay=16, neutralization="SUBINDUSTRY",
                                  truncation=0.05)},
    # 10: zscore wrap + pasteurization=ON (combine fixes)
    {"name": "r41_d0_zscore_pasteur_on",
     "expression": f"zscore({D0_BASE5_PASS})",
     "settings": dict(base_settings_d0(decay=8, neutralization="MARKET",
                                       truncation=0.05),
                      pasteurization="ON")},
]


# =====================================================================
# Round 42: kill CONCENTRATED_WEIGHT=0.167 via ts_backfill on news fields.
# R41 audit (10 sims) showed: 2 alphas now pass SUB_UNIVERSE_SHARPE (decay=16
# helps), but CONCENTRATED_WEIGHT stuck at exactly 0.167 across all variants
# regardless of outer wraps, decay, neutralization, or truncation.
# 1/6 is suspicious -- on sparse-news days the alpha has weight on only ~6
# names. ts_backfill(news_*, 252) carries the news signal forward across
# non-news days, densifying the signal and (hopefully) breaking the 1/6 wall.
# =====================================================================
D0_NEWS_PE_BF    = ("-group_rank(ts_mean(ts_backfill(news_pe_ratio, 252), 22), "
                    "subindustry)")
D0_NEWS_SI_BF    = ("group_rank(ts_mean(ts_backfill(news_short_interest, 252), 22), "
                    "subindustry)")
D0_BASE3_BF      = (f"add(add({D0_NEWS_PE_BF}, {D0_NEWS_SI_BF}), {D0_IV_SKEW180})")
D0_BASE5_BF      = (f"add(add(add(add({D0_NEWS_PE_BF}, {D0_NEWS_SI_BF}), "
                    f"{D0_IV_TS_SLOPE}), {D0_EST_EBIT}), {D0_IV_SKEW180})")

ROUND_42 = [
    # 1: 3-axis ts_backfill, decay=16, MARKET (mirrors R41 MPbK6zKL config that
    #    cleared SUB_SH=0.88 -- now add backfill to kill concentration)
    {"name": "r42_d0_3axis_bf_d16",
     "expression": D0_BASE3_BF,
     "settings": base_settings_d0(decay=16, neutralization="MARKET",
                                  truncation=0.05)},
    # 2: 5-axis ts_backfill, decay=16, MARKET
    {"name": "r42_d0_5axis_bf_d16",
     "expression": D0_BASE5_BF,
     "settings": base_settings_d0(decay=16, neutralization="MARKET",
                                  truncation=0.05)},
    # 3: 3-axis ts_backfill + zscore wrap
    {"name": "r42_d0_3axis_bf_zscore_d16",
     "expression": f"zscore({D0_BASE3_BF})",
     "settings": base_settings_d0(decay=16, neutralization="MARKET",
                                  truncation=0.05)},
    # 4: 5-axis ts_backfill + zscore wrap + SUBINDUSTRY (mirrors Jjng8ORl)
    {"name": "r42_d0_5axis_bf_zscore_subind",
     "expression": f"zscore({D0_BASE5_BF})",
     "settings": base_settings_d0(decay=16, neutralization="SUBINDUSTRY",
                                  truncation=0.05)},
    # 5: 3-axis ts_backfill with decay=8 (less smoothing, to recover SH)
    {"name": "r42_d0_3axis_bf_d8",
     "expression": D0_BASE3_BF,
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
    # 6: 3-axis ts_backfill + decay=32 (very heavy smoothing)
    {"name": "r42_d0_3axis_bf_d32",
     "expression": D0_BASE3_BF,
     "settings": base_settings_d0(decay=32, neutralization="MARKET",
                                  truncation=0.05)},
    # 7: 5-axis ts_backfill + pasteurization=ON
    {"name": "r42_d0_5axis_bf_pasteur",
     "expression": D0_BASE5_BF,
     "settings": dict(base_settings_d0(decay=16, neutralization="MARKET",
                                       truncation=0.05),
                      pasteurization="ON")},
    # 8: 3-axis ts_backfill + winsorize wrap
    {"name": "r42_d0_3axis_bf_winsorize",
     "expression": f"winsorize({D0_BASE3_BF})",
     "settings": base_settings_d0(decay=16, neutralization="MARKET",
                                  truncation=0.05)},
    # 9: 3-axis ts_backfill at trunc=0.03
    {"name": "r42_d0_3axis_bf_t003",
     "expression": D0_BASE3_BF,
     "settings": base_settings_d0(decay=16, neutralization="MARKET",
                                  truncation=0.03)},
    # 10: 5-axis ts_backfill + zscore + MARKET + decay=32 (max smoothing+redistribute)
    {"name": "r42_d0_5axis_bf_zscore_d32",
     "expression": f"zscore({D0_BASE5_BF})",
     "settings": base_settings_d0(decay=32, neutralization="MARKET",
                                  truncation=0.05)},
]


# =====================================================================
# Round 43: tighten ts_backfill window to recover SH >= 1.5.
# R42 confirmed ts_backfill is the right lever -- it fixed SUB_UNIVERSE_SH
# (all >= 0.65, most > 1.0) and dropped CONCENTRATED_WEIGHT from 0.167 to
# 0.125 (one variant hit 0.10). But 252-day backfill over-smoothed and
# killed SH (1.22-1.40, was 1.5+). R43 uses 60/120-day backfill to find
# the SH-vs-concentration sweet spot.
# Best R42: 0mAe6aAq SH=1.40 conc=0.125 sub=0.85 (need SH+0.10, conc-0.025).
# =====================================================================
def _bf_pe(window=60):
    return (f"-group_rank(ts_mean(ts_backfill(news_pe_ratio, {window}), 22), "
            f"subindustry)")

def _bf_si(window=60):
    return (f"group_rank(ts_mean(ts_backfill(news_short_interest, {window}), 22), "
            f"subindustry)")

def _base5_bf(window=60):
    return (f"add(add(add(add({_bf_pe(window)}, {_bf_si(window)}), "
            f"{D0_IV_TS_SLOPE}), {D0_EST_EBIT}), {D0_IV_SKEW180})")

ROUND_43 = [
    # 1: 5-axis bf=60, d=8 MARKET (light backfill)
    {"name": "r43_d0_5axis_bf60_d8",
     "expression": _base5_bf(60),
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
    # 2: 5-axis bf=120, d=8 MARKET
    {"name": "r43_d0_5axis_bf120_d8",
     "expression": _base5_bf(120),
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
    # 3: 5-axis bf=30, d=8 MARKET (very light)
    {"name": "r43_d0_5axis_bf30_d8",
     "expression": _base5_bf(30),
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
    # 4: 5-axis bf=60, d=8, trunc=0.03 (denser signal + tighter cap)
    {"name": "r43_d0_5axis_bf60_d8_t003",
     "expression": _base5_bf(60),
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.03)},
    # 5: 5-axis: backfill ONLY pe (60d), si stays direct
    {"name": "r43_d0_5axis_bf_pe_only",
     "expression": (
         f"add(add(add(add({_bf_pe(60)}, {D0_NEWS_SI_POS}), "
         f"{D0_IV_TS_SLOPE}), {D0_EST_EBIT}), {D0_IV_SKEW180})"
     ),
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
    # 6: 5-axis: backfill ONLY si (60d), pe direct
    {"name": "r43_d0_5axis_bf_si_only",
     "expression": (
         f"add(add(add(add({D0_NEWS_PE}, {_bf_si(60)}), "
         f"{D0_IV_TS_SLOPE}), {D0_EST_EBIT}), {D0_IV_SKEW180})"
     ),
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
    # 7: 7-axis bf=60 + book-to-market + leverage (more axes dilute conc)
    {"name": "r43_d0_7axis_bf60",
     "expression": (
         f"add(add({_base5_bf(60)}, {D0_BOOK_MKT}), {D0_LEVERAGE_POS})"
     ),
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
    # 8: 5-axis bf=60, d=4 (less decay, recover SH)
    {"name": "r43_d0_5axis_bf60_d4",
     "expression": _base5_bf(60),
     "settings": base_settings_d0(decay=4, neutralization="MARKET",
                                  truncation=0.05)},
    # 9: 5-axis bf=60 + winsorize wrap (max conc fix)
    {"name": "r43_d0_5axis_bf60_winsorize",
     "expression": f"winsorize({_base5_bf(60)})",
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
    # 10: 5-axis bf=120 + d=16 + SUBINDUSTRY (alt path)
    {"name": "r43_d0_5axis_bf120_subind_d16",
     "expression": _base5_bf(120),
     "settings": base_settings_d0(decay=16, neutralization="SUBINDUSTRY",
                                  truncation=0.05)},
]


# =====================================================================
# Round 44: dilute CONCENTRATED_WEIGHT on KPnXpmmg (SH=1.77, conc=0.167).
# KPnXpmmg uses backfill on news_pe ONLY, leaving sparse news_short_interest
# to cause 1/6 concentration spikes. R44 strategies:
#   A. backfill BOTH news fields at moderate window (60/90)
#   B. add 3 dense axes (book/leverage/invest) to spread positions
#   C. wrap zscore/winsorize, trunc=0.03
# =====================================================================
KPNX_BASE = (
    f"add(add(add(add({_bf_pe(60)}, {D0_NEWS_SI_POS}), "
    f"{D0_IV_TS_SLOPE}), {D0_EST_EBIT}), {D0_IV_SKEW180})"
)

ROUND_44 = [
    # 1: KPnXpmmg + book + leverage + invest (8-axis, dilute conc)
    {"name": "r44_d0_kpnx_plus_bm_lev_inv",
     "expression": (
         f"add(add(add({KPNX_BASE}, {D0_BOOK_MKT}), "
         f"{D0_LEVERAGE_POS}), {D0_INVEST})"
     ),
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
    # 2: KPnXpmmg + 2 dense + zscore wrap
    {"name": "r44_d0_kpnx_plus_bm_lev_zscore",
     "expression": (
         f"zscore(add(add({KPNX_BASE}, {D0_BOOK_MKT}), {D0_LEVERAGE_POS}))"
     ),
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
    # 3: KPnXpmmg with backfill on BOTH news fields, bf=90
    {"name": "r44_d0_5axis_bf_both90",
     "expression": (
         f"add(add(add(add({_bf_pe(90)}, {_bf_si(90)}), "
         f"{D0_IV_TS_SLOPE}), {D0_EST_EBIT}), {D0_IV_SKEW180})"
     ),
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
    # 4: same as #3 with trunc=0.03
    {"name": "r44_d0_5axis_bf_both90_t003",
     "expression": (
         f"add(add(add(add({_bf_pe(90)}, {_bf_si(90)}), "
         f"{D0_IV_TS_SLOPE}), {D0_EST_EBIT}), {D0_IV_SKEW180})"
     ),
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.03)},
    # 5: KPnXpmmg + trunc=0.03 + winsorize wrap (max conc fixes on the SH winner)
    {"name": "r44_d0_kpnx_winsorize_t003",
     "expression": f"winsorize({KPNX_BASE})",
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.03)},
    # 6: KPnXpmmg + trunc=0.03 alone
    {"name": "r44_d0_kpnx_t003",
     "expression": KPNX_BASE,
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.03)},
    # 7: KPnXpmmg + zscore wrap (continuous redistribution)
    {"name": "r44_d0_kpnx_zscore",
     "expression": f"zscore({KPNX_BASE})",
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
    # 8: 9-axis: KPnXpmmg + bm + lev + inv + dividend
    {"name": "r44_d0_kpnx_plus_4dense",
     "expression": (
         f"add(add(add(add({KPNX_BASE}, {D0_BOOK_MKT}), "
         f"{D0_LEVERAGE_POS}), {D0_INVEST}), {D0_DIV_YIELD})"
     ),
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
    # 9: 5-axis bf BOTH 60d + zscore wrap (densify + redistribute)
    {"name": "r44_d0_5axis_bf_both60_zscore",
     "expression": (
         f"zscore(add(add(add(add({_bf_pe(60)}, {_bf_si(60)}), "
         f"{D0_IV_TS_SLOPE}), {D0_EST_EBIT}), {D0_IV_SKEW180}))"
     ),
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
    # 10: 8-axis + winsorize + trunc=0.03 (max combinational conc fix)
    {"name": "r44_d0_8axis_winsorize_t003",
     "expression": (
         f"winsorize(add(add(add({KPNX_BASE}, {D0_BOOK_MKT}), "
         f"{D0_LEVERAGE_POS}), {D0_INVEST}))"
     ),
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.03)},
]


# =====================================================================
# Round 45: push conc 0.125 -> <=0.1 on R44#3 (P0nwkX8M).
# Best candidate: P0nwkX8M = 5-axis bf BOTH news (90d), MARKET, decay=8,
# trunc=0.05. SH=1.53 FIT=1.45 sub-SH=1.18. Only blocker: conc=0.125 (=1/8).
# Need 0.025 more density. Try: longer backfill windows (120/150),
# ts_backfill on est_ebit too, alternative wraps. R44 showed dilution by
# axes makes it WORSE so stay 5-axis.
# =====================================================================
def _bf_ebit(window=60):
    return (f"group_rank(ts_mean(divide(ts_backfill(est_ebit, {window}), cap), 22), "
            f"subindustry)")

def _bf_iv_skew(window=60):
    return (f"group_rank(ts_mean(ts_backfill(implied_volatility_mean_skew_180, "
            f"{window}), 22), subindustry)")

def _bf_iv_ts(window=60):
    return (f"group_rank(ts_mean(ts_backfill(subtract("
            f"implied_volatility_mean_skew_30, implied_volatility_mean_skew_360), "
            f"{window}), 22), subindustry)")

def _base5_bf_both(window=90, ebit_bf=None, iv_bf=None):
    pe = _bf_pe(window)
    si = _bf_si(window)
    ebit = _bf_ebit(ebit_bf) if ebit_bf else D0_EST_EBIT
    iv_skew = _bf_iv_skew(iv_bf) if iv_bf else D0_IV_SKEW180
    iv_ts = _bf_iv_ts(iv_bf) if iv_bf else D0_IV_TS_SLOPE
    return f"add(add(add(add({pe}, {si}), {iv_ts}), {ebit}), {iv_skew})"

ROUND_45 = [
    # 1: bf news 120, no ebit bf (mid window)
    {"name": "r45_d0_5axis_bf_both120",
     "expression": _base5_bf_both(120),
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
    # 2: bf news 150, no ebit bf
    {"name": "r45_d0_5axis_bf_both150",
     "expression": _base5_bf_both(150),
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
    # 3: bf news 90 + bf ebit 60
    {"name": "r45_d0_5axis_bf_news90_ebit60",
     "expression": _base5_bf_both(90, ebit_bf=60),
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
    # 4: bf news 120 + bf ebit 60
    {"name": "r45_d0_5axis_bf_news120_ebit60",
     "expression": _base5_bf_both(120, ebit_bf=60),
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
    # 5: bf news 120 + bf ALL (ebit+iv 60d)
    {"name": "r45_d0_5axis_bf_all",
     "expression": _base5_bf_both(120, ebit_bf=60, iv_bf=60),
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
    # 6: bf news 120 + zscore wrap (continuous redistribution)
    {"name": "r45_d0_5axis_bf120_zscore",
     "expression": f"zscore({_base5_bf_both(120)})",
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
    # 7: bf news 120 + normalize wrap
    {"name": "r45_d0_5axis_bf120_normalize",
     "expression": f"normalize({_base5_bf_both(120)})",
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
    # 8: bf news 120 + universe TOP1000 (denser universe)
    {"name": "r45_d0_5axis_bf120_top1000",
     "expression": _base5_bf_both(120),
     "settings": dict(base_settings_d0(decay=8, neutralization="MARKET",
                                       truncation=0.05),
                      universe="TOP1000")},
    # 9: bf news 120 + decay=16 (heavier smoothing)
    {"name": "r45_d0_5axis_bf120_d16",
     "expression": _base5_bf_both(120),
     "settings": base_settings_d0(decay=16, neutralization="MARKET",
                                  truncation=0.05)},
    # 10: bf news 120 + pasteurization=ON
    {"name": "r45_d0_5axis_bf120_pasteur",
     "expression": _base5_bf_both(120),
     "settings": dict(base_settings_d0(decay=8, neutralization="MARKET",
                                       truncation=0.05),
                      pasteurization="ON")},
]


# =====================================================================
# Round 46: extend ts_mean window to densify news fields.
# R45 confirmed: ts_backfill(news_*, 90-252d) hits a 0.125 (=1/8) wall.
# news_pe_ratio coverage is 0.97 (NOT a coverage problem) -- the issue is
# DAILY UPDATE PATTERN. ts_mean(news_*, 22) only sees ~1-2 news values per
# stock per month. Extending ts_mean to 60/120/252d covers more news
# values per stock. Pair with backfill for additional carry.
# =====================================================================
def _bf_pe_v2(window, mean_d=22):
    return (f"-group_rank(ts_mean(ts_backfill(news_pe_ratio, {window}), "
            f"{mean_d}), subindustry)")

def _bf_si_v2(window, mean_d=22):
    return (f"group_rank(ts_mean(ts_backfill(news_short_interest, {window}), "
            f"{mean_d}), subindustry)")

def _base5_v2(bf_win, mean_d):
    pe = _bf_pe_v2(bf_win, mean_d)
    si = _bf_si_v2(bf_win, mean_d)
    return (f"add(add(add(add({pe}, {si}), {D0_IV_TS_SLOPE}), "
            f"{D0_EST_EBIT}), {D0_IV_SKEW180})")

# Outer ts_backfill on the GROUP_RANK output (carries rank across NaN days)
def _bf_pe_outer(rank_bf=22):
    return (f"-ts_backfill(group_rank(ts_mean(news_pe_ratio, 22), subindustry), "
            f"{rank_bf})")

def _bf_si_outer(rank_bf=22):
    return (f"ts_backfill(group_rank(ts_mean(news_short_interest, 22), subindustry), "
            f"{rank_bf})")

ROUND_46 = [
    # 1: ts_mean=60d, bf=60d (more values per window)
    {"name": "r46_d0_5axis_mean60_bf60",
     "expression": _base5_v2(60, 60),
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
    # 2: ts_mean=120d, bf=60d
    {"name": "r46_d0_5axis_mean120_bf60",
     "expression": _base5_v2(60, 120),
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
    # 3: ts_mean=252d, bf=60d (year of news)
    {"name": "r46_d0_5axis_mean252_bf60",
     "expression": _base5_v2(60, 252),
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
    # 4: ts_mean=120d, no bf
    {"name": "r46_d0_5axis_mean120_nobf",
     "expression": (f"add(add(add(add(-group_rank(ts_mean(news_pe_ratio, 120), subindustry), "
                    f"group_rank(ts_mean(news_short_interest, 120), subindustry)), "
                    f"{D0_IV_TS_SLOPE}), {D0_EST_EBIT}), {D0_IV_SKEW180})"),
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
    # 5: outer ts_backfill on group_rank output (carry rank across NaN)
    {"name": "r46_d0_5axis_outer_bf30",
     "expression": (f"add(add(add(add({_bf_pe_outer(30)}, {_bf_si_outer(30)}), "
                    f"{D0_IV_TS_SLOPE}), {D0_EST_EBIT}), {D0_IV_SKEW180})"),
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
    # 6: ts_mean=60d + bf=120d
    {"name": "r46_d0_5axis_mean60_bf120",
     "expression": _base5_v2(120, 60),
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
    # 7: ts_mean=60d + bf=252d (max carry)
    {"name": "r46_d0_5axis_mean60_bf252",
     "expression": _base5_v2(252, 60),
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
    # 8: Replace ts_mean with ts_decay_linear (weight recent more, handle NaN better)
    {"name": "r46_d0_5axis_decay_linear60",
     "expression": (f"add(add(add(add(-group_rank(ts_decay_linear("
                    f"news_pe_ratio, 60), subindustry), "
                    f"group_rank(ts_decay_linear(news_short_interest, 60), subindustry)), "
                    f"{D0_IV_TS_SLOPE}), {D0_EST_EBIT}), {D0_IV_SKEW180})"),
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
    # 9: outer bf=60 (longer carry of rank)
    {"name": "r46_d0_5axis_outer_bf60",
     "expression": (f"add(add(add(add({_bf_pe_outer(60)}, {_bf_si_outer(60)}), "
                    f"{D0_IV_TS_SLOPE}), {D0_EST_EBIT}), {D0_IV_SKEW180})"),
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
    # 10: ts_mean=120d + outer bf=30d (combination)
    {"name": "r46_d0_5axis_mean120_outerbf30",
     "expression": (f"add(add(add(add("
                    f"-ts_backfill(group_rank(ts_mean(news_pe_ratio, 120), subindustry), 30), "
                    f"ts_backfill(group_rank(ts_mean(news_short_interest, 120), subindustry), 30)), "
                    f"{D0_IV_TS_SLOPE}), {D0_EST_EBIT}), {D0_IV_SKEW180})"),
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
]


# =====================================================================
# Round 47: thread the needle between R46 #2 (SH=1.57 conc=0.150) and
# R46 #3 (SH=1.22 conc=0.10 EXACT). Need conc<0.1 AND SH>=1.5.
# Fine-grain ts_mean window 160-200d + decay tweaks.
# =====================================================================
ROUND_47 = [
    # 1: mean=160, bf=60 (between 120 and 252)
    {"name": "r47_d0_5axis_mean160_bf60",
     "expression": _base5_v2(60, 160),
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
    # 2: mean=180, bf=60
    {"name": "r47_d0_5axis_mean180_bf60",
     "expression": _base5_v2(60, 180),
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
    # 3: mean=200, bf=60
    {"name": "r47_d0_5axis_mean200_bf60",
     "expression": _base5_v2(60, 200),
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
    # 4: mean=220, bf=60
    {"name": "r47_d0_5axis_mean220_bf60",
     "expression": _base5_v2(60, 220),
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
    # 5: mean=252, bf=60, decay=4 (less local smoothing, recover SH)
    {"name": "r47_d0_5axis_mean252_bf60_d4",
     "expression": _base5_v2(60, 252),
     "settings": base_settings_d0(decay=4, neutralization="MARKET",
                                  truncation=0.05)},
    # 6: mean=252, bf=60, decay=12
    {"name": "r47_d0_5axis_mean252_bf60_d12",
     "expression": _base5_v2(60, 252),
     "settings": base_settings_d0(decay=12, neutralization="MARKET",
                                  truncation=0.05)},
    # 7: mean=200, bf=90
    {"name": "r47_d0_5axis_mean200_bf90",
     "expression": _base5_v2(90, 200),
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
    # 8: mean=180, bf=120
    {"name": "r47_d0_5axis_mean180_bf120",
     "expression": _base5_v2(120, 180),
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
    # 9: mean=200, bf=60, trunc=0.03 (denser signal + tighter cap)
    {"name": "r47_d0_5axis_mean200_bf60_t003",
     "expression": _base5_v2(60, 200),
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.03)},
    # 10: mean=180, bf=60, decay=4
    {"name": "r47_d0_5axis_mean180_bf60_d4",
     "expression": _base5_v2(60, 180),
     "settings": base_settings_d0(decay=4, neutralization="MARKET",
                                  truncation=0.05)},
]


# =====================================================================
# Round 48: break 1/8 conc wall via drop-one-axis tests + dense sentiment
# proxies. R47 confirmed conc=0.125 (=1/8) wall persists with all 5
# axes regardless of mean/bf windows; SH-vs-conc tradeoff is steep.
# Two strategies:
#   A) drop-one-axis (5 sims): identify which axis spikes conc
#   B) replace sparse news_si with dense socialmedia (cov=1.0):
#      scl12_sentiment, snt_buzz, snt_value
# Base: LLnnnoo9 config (mean=200, bf=90, MARKET, decay=8, trunc=0.05)
# =====================================================================
def _pe_v3():    return "-group_rank(ts_mean(ts_backfill(news_pe_ratio, 90), 200), subindustry)"
def _si_v3():    return "group_rank(ts_mean(ts_backfill(news_short_interest, 90), 200), subindustry)"
def _ivts_v3():  return D0_IV_TS_SLOPE
def _ebit_v3(): return D0_EST_EBIT
def _ivskew_v3(): return D0_IV_SKEW180

# Dense sentiment proxies (cov=1.0)
D0_SENT_DENSE   = "-group_rank(ts_mean(scl12_sentiment, 60), subindustry)"
D0_SENT_NEG     = "group_rank(ts_mean(snt_value, 60), subindustry)"
D0_SENT_BUZZ    = "group_rank(ts_mean(snt_buzz, 60), subindustry)"

ROUND_48 = [
    # 1: drop news_pe (4-axis: si, iv_ts, ebit, ivskew)
    {"name": "r48_d0_drop_pe",
     "expression": f"add(add(add({_si_v3()}, {_ivts_v3()}), {_ebit_v3()}), {_ivskew_v3()})",
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
    # 2: drop news_si (4-axis: pe, iv_ts, ebit, ivskew)
    {"name": "r48_d0_drop_si",
     "expression": f"add(add(add({_pe_v3()}, {_ivts_v3()}), {_ebit_v3()}), {_ivskew_v3()})",
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
    # 3: drop iv_ts (4-axis)
    {"name": "r48_d0_drop_ivts",
     "expression": f"add(add(add({_pe_v3()}, {_si_v3()}), {_ebit_v3()}), {_ivskew_v3()})",
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
    # 4: drop est_ebit (4-axis)
    {"name": "r48_d0_drop_ebit",
     "expression": f"add(add(add({_pe_v3()}, {_si_v3()}), {_ivts_v3()}), {_ivskew_v3()})",
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
    # 5: drop iv_skew (4-axis)
    {"name": "r48_d0_drop_ivskew",
     "expression": f"add(add(add({_pe_v3()}, {_si_v3()}), {_ivts_v3()}), {_ebit_v3()})",
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
    # 6: REPLACE news_si with scl12_sentiment (dense)
    {"name": "r48_d0_si_to_scl_sent",
     "expression": (f"add(add(add(add({_pe_v3()}, {D0_SENT_DENSE}), "
                    f"{_ivts_v3()}), {_ebit_v3()}), {_ivskew_v3()})"),
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
    # 7: REPLACE news_si with snt_value (dense)
    {"name": "r48_d0_si_to_snt_value",
     "expression": (f"add(add(add(add({_pe_v3()}, {D0_SENT_NEG}), "
                    f"{_ivts_v3()}), {_ebit_v3()}), {_ivskew_v3()})"),
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
    # 8: REPLACE news_si with snt_buzz
    {"name": "r48_d0_si_to_snt_buzz",
     "expression": (f"add(add(add(add({_pe_v3()}, {D0_SENT_BUZZ}), "
                    f"{_ivts_v3()}), {_ebit_v3()}), {_ivskew_v3()})"),
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
    # 9: ADD scl12_sentiment as 6th axis (keep all 5 originals)
    {"name": "r48_d0_5axis_plus_scl_sent",
     "expression": (f"add({_base5_v2(90, 200)}, {D0_SENT_DENSE})"),
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
    # 10: ADD snt_buzz as 6th axis
    {"name": "r48_d0_5axis_plus_snt_buzz",
     "expression": (f"add({_base5_v2(90, 200)}, {D0_SENT_BUZZ})"),
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
]


# =====================================================================
# Round 49: recover SH>=1.5 on news-si-free base (conc-clean).
# R48 confirmed news_short_interest IS the concentrator. Dropping it
# (N1nnrM98) gives C_WEIGHT=PASS but SH=1.16. Need +0.4 SH via dense
# axis additions: invest (R36 0.87), leverage (0.73), book/market (0.72),
# dividend, scl12_sentiment (dense socialmedia), snt_buzz, etc.
# Base = 4-axis (bf_pe + iv_ts + est_ebit + iv_skew) at mean=200, bf=90.
# =====================================================================
BASE4_NO_SI = f"add(add(add({_pe_v3()}, {_ivts_v3()}), {_ebit_v3()}), {_ivskew_v3()})"

ROUND_49 = [
    # 1: base + invest (5-axis)
    {"name": "r49_d0_4ax_plus_invest",
     "expression": f"add({BASE4_NO_SI}, {D0_INVEST})",
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
    # 2: base + invest + leverage (6-axis)
    {"name": "r49_d0_4ax_plus_invest_lev",
     "expression": f"add(add({BASE4_NO_SI}, {D0_INVEST}), {D0_LEVERAGE_POS})",
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
    # 3: base + invest + leverage + bm (7-axis dense)
    {"name": "r49_d0_4ax_plus_invest_lev_bm",
     "expression": (f"add(add(add({BASE4_NO_SI}, {D0_INVEST}), "
                    f"{D0_LEVERAGE_POS}), {D0_BOOK_MKT})"),
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
    # 4: base + scl12_sentiment (5-axis with sentiment)
    {"name": "r49_d0_4ax_plus_sclsent",
     "expression": f"add({BASE4_NO_SI}, {D0_SENT_DENSE})",
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
    # 5: base + scl_sent + invest (6-axis)
    {"name": "r49_d0_4ax_plus_sclsent_invest",
     "expression": f"add(add({BASE4_NO_SI}, {D0_SENT_DENSE}), {D0_INVEST})",
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
    # 6: base + snt_buzz + leverage
    {"name": "r49_d0_4ax_plus_buzz_lev",
     "expression": f"add(add({BASE4_NO_SI}, {D0_SENT_BUZZ}), {D0_LEVERAGE_POS})",
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
    # 7: base + 4 dense (invest + lev + bm + scl_sent) -- 8-axis
    {"name": "r49_d0_4ax_plus_4dense",
     "expression": (f"add(add(add(add({BASE4_NO_SI}, {D0_INVEST}), "
                    f"{D0_LEVERAGE_POS}), {D0_BOOK_MKT}), {D0_SENT_DENSE})"),
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
    # 8: base + snt_value (negative sentiment, short-side proxy) + invest
    {"name": "r49_d0_4ax_plus_sntval_invest",
     "expression": f"add(add({BASE4_NO_SI}, {D0_SENT_NEG}), {D0_INVEST})",
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
    # 9: 4ax + invest + lev + dividend_yield
    {"name": "r49_d0_4ax_plus_invest_lev_div",
     "expression": (f"add(add(add({BASE4_NO_SI}, {D0_INVEST}), "
                    f"{D0_LEVERAGE_POS}), {D0_DIV_YIELD})"),
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
    # 10: 4ax + 3 dense + IV_skew at different window (30d)
    {"name": "r49_d0_4ax_plus_invest_lev_bm_alt",
     "expression": (f"add(add(add(add({BASE4_NO_SI}, {D0_INVEST}), "
                    f"{D0_LEVERAGE_POS}), {D0_BOOK_MKT}), "
                    f"group_rank(ts_mean(implied_volatility_mean_skew_30, 22), subindustry))"),
     "settings": base_settings_d0(decay=8, neutralization="MARKET",
                                  truncation=0.05)},
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
    elif args.round == 18:
        batch = ROUND_18
    elif args.round == 19:
        batch = ROUND_19
    elif args.round == 20:
        batch = ROUND_20
    elif args.round == 21:
        batch = ROUND_21
    elif args.round == 22:
        batch = ROUND_22
    elif args.round == 23:
        batch = ROUND_23
    elif args.round == 24:
        batch = ROUND_24
    elif args.round == 25:
        batch = ROUND_25
    elif args.round == 26:
        batch = ROUND_26
    elif args.round == 27:
        batch = ROUND_27
    elif args.round == 28:
        batch = ROUND_28
    elif args.round == 29:
        batch = ROUND_29
    elif args.round == 30:
        batch = ROUND_30
    elif args.round == 31:
        batch = ROUND_31
    elif args.round == 32:
        batch = ROUND_32
    elif args.round == 33:
        batch = ROUND_33
    elif args.round == 34:
        batch = ROUND_34
    elif args.round == 35:
        batch = ROUND_35
    elif args.round == 36:
        batch = ROUND_36
    elif args.round == 37:
        batch = ROUND_37
    elif args.round == 38:
        batch = ROUND_38
    elif args.round == 39:
        batch = ROUND_39
    elif args.round == 40:
        batch = ROUND_40
    elif args.round == 41:
        batch = ROUND_41
    elif args.round == 42:
        batch = ROUND_42
    elif args.round == 43:
        batch = ROUND_43
    elif args.round == 44:
        batch = ROUND_44
    elif args.round == 45:
        batch = ROUND_45
    elif args.round == 46:
        batch = ROUND_46
    elif args.round == 47:
        batch = ROUND_47
    elif args.round == 48:
        batch = ROUND_48
    elif args.round == 49:
        batch = ROUND_49
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
