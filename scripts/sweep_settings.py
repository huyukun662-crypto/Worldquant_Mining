"""Sweep one expression across universe x neutralization x decay settings.

Submits the SAME D0 expression under different (universe, neutralization)
combos so we can find the settings that lift IS Sharpe past the submit
gate, then report IS metrics + checks for each.

Usage:
    python scripts/sweep_settings.py "EXPR"
"""
from __future__ import annotations
import sys, json, itertools
import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("d0", REPO / "scripts" / "d0_mine.py")
d0 = importlib.util.module_from_spec(spec); spec.loader.exec_module(d0)

UNIVERSES = ["TOP3000", "TOP1000", "TOP500", "TOP200"]
NEUTS = ["MARKET", "SECTOR", "INDUSTRY", "SUBINDUSTRY"]


def main():
    expr = sys.argv[1]
    combos = sys.argv[2] if len(sys.argv) > 2 else "default"
    s = d0.auth()
    print("authenticated", file=sys.stderr)
    out = []
    if combos == "uni":
        grid = [(u, "MARKET") for u in UNIVERSES]
    elif combos == "neut":
        grid = [("TOP3000", n) for n in NEUTS]
    else:
        grid = list(itertools.product(["TOP3000", "TOP1000", "TOP500"], ["MARKET", "INDUSTRY", "SUBINDUSTRY"]))
    for uni, neut in grid:
        print(f"\n=== universe={uni} neut={neut}")
        r = d0.submit(s, expr, {"universe": uni, "neutralization": neut})
        d0.print_result(r)
        if r.get("ok"):
            r["_uni"] = uni; r["_neut"] = neut
        out.append(r)
    json.dump(out, open("SWEEP_RESULTS.json", "w"), indent=2, default=str)
    # summary
    print("\n" + "=" * 70)
    for r in out:
        if r.get("ok"):
            print(f"{r.get('_uni'):<9}{r.get('_neut'):<13} SH={r['sharpe']:.3f} "
                  f"FIT={r['fitness']:.2f} TO={r['turnover']:.3f} DD={r['drawdown']:.3f}")


if __name__ == "__main__":
    main()
