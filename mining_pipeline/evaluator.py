"""Expression evaluator.

Parses a FASTEXPR-style alpha expression into a Python AST, then walks
the AST to compute the (T, N) factor signal on a Panel.

Supported syntax:
- function calls: `op(arg, arg, ...)`
- numeric literals: `5`, `0.5`, `-1`
- field references: `close`, `open`, `high`, `low`, `volume`, `vwap`,
  `returns`, `adv5`, `adv20`, `adv60` (computed on demand)
- arithmetic operators: `+ - * /` and unary `-`

Anything else raises `ValueError` -- the generator only emits a
restricted subset of operators so this is intentional.
"""

from __future__ import annotations

import ast
import operator as op_mod
from typing import Dict

import numpy as np

from .data import Panel
from .operators import NUMPY_OPS, ts_mean


_BINOP = {
    ast.Add:      op_mod.add,
    ast.Sub:      op_mod.sub,
    ast.Mult:     op_mod.mul,
    ast.Div:      op_mod.truediv,
    ast.USub:     op_mod.neg,
    ast.UAdd:     lambda x: x,
}


def _fields(panel: Panel) -> Dict[str, np.ndarray]:
    """Lazy field dictionary."""
    base = {
        "open": panel.open, "high": panel.high, "low": panel.low,
        "close": panel.close, "volume": panel.volume,
        "vwap": panel.vwap, "returns": panel.returns,
        "dollar_volume": panel.close * panel.volume,
    }
    # Common adv windows
    for d in (5, 10, 20, 30, 60, 120):
        base[f"adv{d}"] = ts_mean(panel.close * panel.volume, d)
    return base


class Evaluator:
    def __init__(self, panel: Panel):
        self.panel = panel
        self._fields = _fields(panel)

    def evaluate(self, expr: str) -> np.ndarray:
        tree = ast.parse(expr, mode="eval")
        return self._eval(tree.body)

    def _eval(self, node):
        if isinstance(node, ast.Constant):
            v = node.value
            if isinstance(v, bool):
                return v
            return v  # preserve int vs float so operators like ts_sum can slice
        if isinstance(node, ast.UnaryOp):
            return _BINOP[type(node.op)](self._eval(node.operand))
        if isinstance(node, ast.BinOp):
            l = self._eval(node.left)
            r = self._eval(node.right)
            return _BINOP[type(node.op)](l, r)
        if isinstance(node, ast.Name):
            if node.id in self._fields:
                return self._fields[node.id]
            raise ValueError(f"unknown field: {node.id}")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise ValueError("only direct function calls allowed")
            fname = node.func.id
            if fname not in NUMPY_OPS:
                raise ValueError(f"unknown operator: {fname}")
            args = [self._eval(a) for a in node.args]
            return NUMPY_OPS[fname](*args)
        raise ValueError(f"unsupported AST node: {type(node).__name__}")
