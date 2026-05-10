"""Initial screening filter.

Per user spec:
    Sharpe > 1.25 AND turnover < 0.25
"""

from __future__ import annotations

from dataclasses import dataclass

from .backtest import BTResult


SHARPE_FLOOR = 1.25
TURNOVER_CEILING = 0.25


@dataclass
class ScreenResult:
    passed: bool
    sharpe: float
    turnover: float
    reason: str


def screen(bt: BTResult,
           sharpe_floor: float = SHARPE_FLOOR,
           turnover_ceiling: float = TURNOVER_CEILING) -> ScreenResult:
    if bt.sharpe <= sharpe_floor:
        return ScreenResult(False, bt.sharpe, bt.turnover,
                            f"sharpe={bt.sharpe:.2f} <= {sharpe_floor}")
    if bt.turnover >= turnover_ceiling:
        return ScreenResult(False, bt.sharpe, bt.turnover,
                            f"turnover={bt.turnover:.3f} >= {turnover_ceiling}")
    return ScreenResult(True, bt.sharpe, bt.turnover, "ok")
