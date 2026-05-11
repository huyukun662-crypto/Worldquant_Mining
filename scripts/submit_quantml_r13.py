"""QuantML round 13: 5 new shapes with bespoke settings.

R12 showed smaller universes hurt every factor on this account tier
(R4_02: 0.94 -> 0.24 on TOP500; R8_03: 1.50 -> 1.13 on TOP500).
TOP3000 stays. Free-tuning the other levers:

  R13_01  body-skew (R10_04) tuned     100d window, decay=8, MARKET
  R13_02  ARCH-style vol persistence   corr(short_vol, long_vol, 60)
  R13_03  fast mean reversion          5d mean vs current, NONE-neut
  R13_04  market-mag co-coupling       corr(returns, |group_mean|)
  R13_05  volume CV                     std(volume)/mean(volume) 60d

Five distinct shapes -- skew, correlation, ratio, correlation, ratio.
Each setting tuple chosen to match the factor's natural horizon.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_runner import run_round  # noqa: E402

FACTORS: list[dict] = [
    {
        "id": "QM_R13_01",
        "category": "body-skew-100d",
        "idea": (
            "R10_04 (intraday body skew) lengthened to 100d window. "
            "Long-window 3rd moment more stable; MARKET-neut since "
            "skew is shape-only."
        ),
        "original": "-Skew((C-O)/O, 100)",
        "expression": (
            "-1 * ts_mean(power(ts_zscore("
            "(close - open) / open, 100), 3), 100)"
        ),
        "settings_override": {
            "universe": "TOP3000",
            "decay": 8,
            "neutralization": "MARKET",
            "truncation": 0.08,
        },
    },
    {
        "id": "QM_R13_02",
        "category": "vol-persistence-corr",
        "idea": (
            "Correlation between 5d and 20d std of returns over 60d. "
            "High corr = vol regime is stable / persistent. Short "
            "high-persistence names (regime-uncertainty premium "
            "reversed: persistent calm reverts to noisy)."
        ),
        "original": "-Corr(Std(Ret,5), Std(Ret,20), 60)",
        "expression": (
            "-1 * ts_corr(ts_std_dev(returns, 5), "
            "ts_std_dev(returns, 20), 60)"
        ),
        "settings_override": {
            "universe": "TOP3000",
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.08,
        },
    },
    {
        "id": "QM_R13_03",
        "category": "fast-mean-reversion",
        "idea": (
            "Short-window mean-reversion: 5d mean vs current. "
            "NONE-neut keeps the raw signal direction; decay=8 to "
            "compress the inherently high TO of a 5d signal."
        ),
        "original": "-(Close/Mean(Close,5) - 1)",
        "expression": "-1 * (close / ts_mean(close, 5) - 1)",
        "settings_override": {
            "universe": "TOP3000",
            "decay": 8,
            "neutralization": "NONE",
            "truncation": 0.08,
        },
    },
    {
        "id": "QM_R13_04",
        "category": "market-mag-coupling",
        "idea": (
            "60d correlation between name return and absolute market "
            "mean return. Captures down-market beta: high coupling = "
            "name moves with market vol. Sign negative -- low coup-"
            "ling earns risk premium."
        ),
        "original": "-Corr(Ret, |MktRet|, 60)",
        "expression": (
            "-1 * ts_corr(returns, abs(group_mean(returns, 1, market)), 60)"
        ),
        "settings_override": {
            "universe": "TOP3000",
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.08,
        },
    },
    {
        "id": "QM_R13_05",
        "category": "volume-cv",
        "idea": (
            "Coefficient of variation of volume over 60d = "
            "std(volume)/mean(volume). Captures volume regime "
            "stability (vs absolute level). High CV = sporadic "
            "trading -> short."
        ),
        "original": "-Std(Vol,60)/Mean(Vol,60)",
        "expression": (
            "-1 * ts_std_dev(volume, 60) / ts_mean(volume, 60)"
        ),
        "settings_override": {
            "universe": "TOP3000",
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.08,
        },
    },
]


if __name__ == "__main__":
    sys.exit(
        run_round(
            FACTORS,
            results_path=Path(__file__).resolve().parent.parent
            / "WQ_QUANTML_RESULTS.json",
            append=True,
        )
    )
