"""QuantML round PZ1: pure PV + non-mdl77 alpha-data, no open/close/mdl77.

Allowed fields:
  PV-only: high, low, volume, vwap, adv20, cap, returns
  Alt-data: snt_buzz, snt_value, news_indx_perf
  Group: subindustry, industry, market (for neutralization context)

5 structurally distinct shapes never tried on PV-only:

  PZ1_01  Volume × range co-movement: ts_corr(volume, high-low, 250)
  PZ1_02  Double PV CoV: -CoV(volume,100) * CoV(high-low,100)
  PZ1_03  VWAP autocorr: ts_corr(vwap, ts_delay(vwap,5), 500)
  PZ1_04  Short/long MAC vwap ratio: MAC(vwap,30)/MAC(vwap,250)
  PZ1_05  Volume delta skewness: -ts_skewness(ts_delta(volume,1), 100)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_runner import run_round  # noqa: E402


def cov_expr(expr: str, w: int = 100) -> str:
    return f"ts_std_dev({expr}, {w}) / ts_mean({expr}, {w})"


def mac(field: str, w: int = 100) -> str:
    return f"ts_mean(abs(ts_delta({field}, 1)), {w}) / ts_mean({field}, {w})"


def winz(expr: str, std: float = 3.0) -> str:
    return f"winsorize({expr}, std={std})"


SET_IND = {
    "universe": "TOP3000", "decay": 4,
    "neutralization": "INDUSTRY", "truncation": 0.05,
}
SET_IND_T10 = {
    "universe": "TOP3000", "decay": 4,
    "neutralization": "INDUSTRY", "truncation": 0.10,
}


FACTORS: list[dict] = [
    {
        "id": "QM_PZ1_01",
        "category": "vol-range-corr",
        "idea": "ts_corr(volume, high-low, 250) -- when volume tracks range, weak alpha.",
        "original": "-ts_corr(volume, high-low, 250)",
        "expression": "-1 * ts_corr(volume, high - low, 250)",
        "settings_override": SET_IND,
    },
    {
        "id": "QM_PZ1_02",
        "category": "double-PV-CoV",
        "idea": "Pure PV: CoV(volume) * CoV(high-low) winsorize.",
        "original": "-winsorize(CoV(volume)*CoV(HL), 3)",
        "expression": winz(
            f"-1 * {cov_expr('volume')} * {cov_expr('high - low')}"
        ),
        "settings_override": SET_IND_T10,
    },
    {
        "id": "QM_PZ1_03",
        "category": "vwap-autocorr",
        "idea": "VWAP autocorrelation 5-day lag, 500-day window.",
        "original": "-ts_corr(vwap, delay(vwap,5), 500)",
        "expression": "-1 * ts_corr(vwap, ts_delay(vwap, 5), 500)",
        "settings_override": SET_IND,
    },
    {
        "id": "QM_PZ1_04",
        "category": "vwap-MAC-ratio",
        "idea": "Term-structure of VWAP shocks: MAC(vwap,30)/MAC(vwap,250).",
        "original": "-winsorize(MAC(vwap,30)/MAC(vwap,250), 3)",
        "expression": winz(f"-1 * {mac('vwap', 30)} / {mac('vwap', 250)}"),
        "settings_override": SET_IND_T10,
    },
    {
        "id": "QM_PZ1_05",
        "category": "volume-delta-skew",
        "idea": "Skewness of volume deltas captures asymmetric volume jumps.",
        "original": "-ts_skewness(ts_delta(volume,1), 100)",
        "expression": "-1 * ts_skewness(ts_delta(volume, 1), 100)",
        "settings_override": SET_IND_T10,
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
