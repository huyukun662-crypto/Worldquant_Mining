"""QuantML round 23: 2 more orthogonal shapes.

Existing 5 viables:
  R6_01, OA24, R16_05  -- OHLC channel statistics
  R8_03                -- session-mean decomposition
  R22_02F              -- volume-weighted return mean

R23 tries:
  R23_01  adv-relative volume   -- volume / adv20 averaged 60d
                                  pure liquidity shock signal
  R23_02  peer-distance          -- (close - subindustry_mean(close))/close
                                  cross-stock relative price level
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_runner import run_round  # noqa: E402

FACTORS: list[dict] = [
    {
        "id": "QM_R23_01",
        "category": "adv-relative-volume",
        "idea": (
            "60d mean of volume / adv20 (adv20 = avg dollar volume "
            "over 20d). Captures persistent above-baseline trading. "
            "Sign negative: short high-relative-volume names "
            "(attention-driven, mean-reverts)."
        ),
        "original": "-Mean(Vol / Adv20, 60)",
        "expression": "-1 * ts_mean(volume / adv20, 60)",
        "settings_override": {
            "universe": "TOP3000",
            "decay": 4,
            "neutralization": "INDUSTRY",
            "truncation": 0.05,
        },
    },
    {
        "id": "QM_R23_02",
        "category": "peer-distance",
        "idea": (
            "60d mean of (close - subindustry mean close)/close. "
            "Cross-stock relative price level (peer distance). "
            "Sign negative: short names trading far above their "
            "sub-industry peers (peer mean reversion)."
        ),
        "original": "-Mean((C - GroupMean(C, SubInd))/C, 60)",
        "expression": (
            "-1 * ts_mean("
            "(close - group_mean(close, 1, subindustry)) / close, 60)"
        ),
        "settings_override": {
            "universe": "TOP3000",
            "decay": 4,
            "neutralization": "INDUSTRY",
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
