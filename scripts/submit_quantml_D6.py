"""QuantML round D6: push illiq-vol toward SH=1.75 + new obscure-field shapes.

D5 results: best obscure-only single = D5_03 (illiq-vol SUBIND) SH=1.10.
Gap to gate (1.75) is 0.65 SH.

Strategies for D6:
  1. MARKET-neut variant of illiq-vol     (D5_03 was SUBIND -> try MARKET)
  2. illiq-vol W500 with extended poll     (D5_02 timed out at 600s; raised to 1200s)
  3. ts_std_dev shape applied to NLPRICE   (parallel obscure field)
  4. ts_std_dev shape applied to NLMKTCAP  (parallel obscure field)
  5. ts_std_dev applied to BAP20D          (bid-ask proxy, parallel obscure)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_runner import run_round  # noqa: E402

FACTORS: list[dict] = [
    {
        "id": "QM_D6_01",
        "category": "illiq-vol-MKT-t10",
        "idea": (
            "D5_03 SUBIND lifted SH from 1.00 to 1.10. Try MARKET-neut "
            "(further looseness) + trunc=0.10. Worked for peer-distance "
            "factor (R23_02 1.06 -> 1.34)."
        ),
        "original": "-Std(milliq, 250)",
        "expression": (
            "-1 * ts_std_dev(mdl77_liquidityriskfactor_milliq, 250)"
        ),
        "settings_override": {
            "universe": "TOP3000",
            "decay": 4,
            "neutralization": "MARKET",
            "truncation": 0.10,
        },
    },
    {
        "id": "QM_D6_02",
        "category": "illiq-vol-W500-retry",
        "idea": (
            "Retry D5_02 with raised poll timeout (1200s). W500 + d=2 + "
            "tight trunc is the PV winning recipe."
        ),
        "original": "-Std(milliq, 500)",
        "expression": (
            "-1 * ts_std_dev(mdl77_liquidityriskfactor_milliq, 500)"
        ),
        "settings_override": {
            "universe": "TOP3000",
            "decay": 2,
            "neutralization": "SUBINDUSTRY",
            "truncation": 0.03,
        },
    },
    {
        "id": "QM_D6_03",
        "category": "nlprice-vol",
        "idea": (
            "Apply the illiq-vol shape to NLPRICE (log of close price). "
            "ts_std_dev(nlprice, 250) -- captures price-level regime "
            "instability. uc=1 on the field. SUBIND d=4 t=0.05."
        ),
        "original": "-Std(nlprice, 250)",
        "expression": (
            "-1 * ts_std_dev(mdl77_2liquidityriskfactor_nlprice, 250)"
        ),
        "settings_override": {
            "universe": "TOP3000",
            "decay": 4,
            "neutralization": "SUBINDUSTRY",
            "truncation": 0.05,
        },
    },
    {
        "id": "QM_D6_04",
        "category": "nlmktcap-vol",
        "idea": (
            "ts_std_dev(nlmktcap, 250) -- market-cap regime instability. "
            "Names whose log-cap variance is HIGH have unstable scale. "
            "Sign negative."
        ),
        "original": "-Std(nlmktcap, 250)",
        "expression": (
            "-1 * ts_std_dev("
            "mdl77_liquidityriskfactor_nlmktcap, 250)"
        ),
        "settings_override": {
            "universe": "TOP3000",
            "decay": 4,
            "neutralization": "SUBINDUSTRY",
            "truncation": 0.05,
        },
    },
    {
        "id": "QM_D6_05",
        "category": "bap20d-vol",
        "idea": (
            "ts_std_dev(bap20d, 250). BAP20D is a 20d bid-ask spread "
            "proxy. Variance of spread = micro-liquidity instability."
        ),
        "original": "-Std(bap20d, 250)",
        "expression": (
            "-1 * ts_std_dev("
            "mdl77_liquidityriskfactor_bap20d, 250)"
        ),
        "settings_override": {
            "universe": "TOP3000",
            "decay": 4,
            "neutralization": "SUBINDUSTRY",
            "truncation": 0.05,
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
