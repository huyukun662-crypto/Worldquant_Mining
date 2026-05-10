"""Translate Qlib-syntax factors from QuantMLResearch's
factor_zoo/runs.md into WQ Brain Fast Expression syntax, and pick
the top-K by |icir| for canonical evaluation on WQ Brain.

Source page (markdown table):
    https://github.com/QuantMLResearch/QuantML/blob/main/factor_zoo/runs.md

Translation map (Qlib -> WQ Fast Expression):

    $close, $open, $high, $low, $volume -> close, open, high, low, volume
    $total_turnover/($volume+1e-12)     -> vwap   (avg traded price proxy)
    Min(x, N)                           -> ts_min(x, N)
    Max(x, N)                           -> ts_max(x, N)
    Mean(x, N)                          -> ts_mean(x, N)
    Std(x, N)                           -> ts_std_dev(x, N)
    Sum(x, N)                           -> ts_sum(x, N)
    Med(x, N)                           -> ts_mean(x, N)         (proxy: WQ has no ts_median)
    Mad(x, N)                           -> ts_mean(abs(x-ts_mean(x,N)),N)
    IdxMin(x, N)                        -> ts_arg_min(x, N)
    IdxMax(x, N)                        -> ts_arg_max(x, N)
    Rank(x, N)                          -> ts_rank(x, N)
    Corr(x, y, N)                       -> ts_corr(x, y, N)
    Ref(x, N)                           -> ts_delay(x, N)
    DownResample(x, N, "last")          -> x     (drop; we evaluate per-day)

Factors using `Peak`, `Skew`, `Kurt`, `Slope`, `Rsquare`, `Resi`,
`Partial`, `PartialRatio`, `DownStd`, `UpStd`, `num_trades`,
`s_dq_freeturnover` are skipped -- the operator/field has no
direct WQ Fast Expression equivalent on this account tier.

Output is a JSON in the shape `extract_uncorrelated.py` /
`pipeline.py` produce, so it can be fed to
`mining_pipeline.wq_pipeline --from-report --freeze-windows`.

Usage:
    python scripts/translate_qml_factors.py /tmp/qml_runs.md \
        --top 10 --out QML_FACTORS_TRANSLATED.json
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


# Operators we can NOT translate -> a factor referencing any of these
# is skipped entirely.
UNSUPPORTED = {
    "Peak", "Skew", "Kurt", "Slope", "Rsquare", "Resi",
    "Partial", "PartialRatio", "DownStd", "UpStd",
}
UNSUPPORTED_FIELDS = {"num_trades", "s_dq_freeturnover"}


def parse_runs_md(path: Path) -> list[dict]:
    """Parse the markdown table; return list of {expr, ic_mean, icir}."""
    out: list[dict] = []
    for line in path.read_text().splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.split("|")[1:-1]]
        if len(cells) < 3:
            continue
        if cells[0] == "factor_name" or set(cells[0]) <= {":", "-"}:
            continue
        try:
            ic = float(cells[1])
            icir = float(cells[2])
        except ValueError:
            continue
        out.append({"expr": cells[0], "ic_mean": ic, "icir": icir})
    return out


def is_translatable(expr: str) -> bool:
    if any(re.search(rf"\b{op}\(", expr) for op in UNSUPPORTED):
        return False
    if any(f in expr for f in UNSUPPORTED_FIELDS):
        return False
    return True


def strip_downresample(expr: str) -> str:
    """Drop the outer DownResample(..., 240, "last") wrapper. The wrapper
    only matters when the underlying data is intra-day; we evaluate at
    daily frequency so the wrapper is identity."""
    # Match DownResample( <inner> , 240, "last" )  -- need balanced parens
    if not expr.startswith("DownResample("):
        return expr
    # Find matching close paren for the outermost DownResample
    depth = 0
    start = expr.index("(")
    for i in range(start, len(expr)):
        if expr[i] == "(":
            depth += 1
        elif expr[i] == ")":
            depth -= 1
            if depth == 0:
                inside = expr[start + 1:i]
                # inside ends with ', 240, "last"' typically
                # strip the trailing comma + arg pair
                # find last comma at depth 0 within `inside`
                d2 = 0
                last_commas: list[int] = []
                for j, ch in enumerate(inside):
                    if ch == "(":
                        d2 += 1
                    elif ch == ")":
                        d2 -= 1
                    elif ch == "," and d2 == 0:
                        last_commas.append(j)
                if len(last_commas) >= 2:
                    inner = inside[: last_commas[-2]]
                else:
                    inner = inside
                return inner.strip()
    return expr


# Order matters: translate vwap composite first so the embedded $total_turnover
# / $volume is consumed before the bare $volume rule fires.
def translate(expr: str) -> str:
    e = strip_downresample(expr)

    # Composite -> vwap. Uses (...) so we tolerate small whitespace.
    e = re.sub(r"\$total_turnover\s*/\s*\(\s*\$volume\s*\+\s*1e-12\s*\)", "vwap", e)
    e = re.sub(r"\$total_turnover\s*/\s*\$volume", "vwap", e)
    # Bare fields
    for src, dst in (("$close", "close"), ("$open", "open"),
                     ("$high", "high"), ("$low", "low"),
                     ("$volume", "volume"),
                     ("$total_turnover", "multiply(vwap, volume)")):
        e = e.replace(src, dst)

    # Operator name maps (regex w/ word boundary so we don't munge identifiers)
    op_map = [
        (r"\bMin\(",    "ts_min("),
        (r"\bMax\(",    "ts_max("),
        (r"\bMean\(",   "ts_mean("),
        (r"\bStd\(",    "ts_std_dev("),
        (r"\bSum\(",    "ts_sum("),
        (r"\bMed\(",    "ts_mean("),    # proxy: WQ has no ts_median on this tier
        (r"\bIdxMin\(", "ts_arg_min("),
        (r"\bIdxMax\(", "ts_arg_max("),
        (r"\bRank\(",   "ts_rank("),
        (r"\bCorr\(",   "ts_corr("),
        (r"\bRef\(",    "ts_delay("),
    ]
    for pat, sub in op_map:
        e = re.sub(pat, sub, e)

    # Mad(x, N) -> ts_mean(abs(subtract(x, ts_mean(x, N))), N)
    e = expand_mad(e)

    return e


def expand_mad(e: str) -> str:
    """Replace each Mad(<x>, <N>) with the algebraic equivalent."""
    while True:
        m = re.search(r"\bMad\(", e)
        if not m:
            break
        i = m.end() - 1
        depth = 1
        j = i + 1
        while j < len(e) and depth > 0:
            if e[j] == "(": depth += 1
            elif e[j] == ")": depth -= 1
            j += 1
        # inside is e[i+1:j-1]
        inside = e[i + 1:j - 1]
        # Split top-level args
        d = 0
        commas: list[int] = []
        for k, ch in enumerate(inside):
            if ch == "(": d += 1
            elif ch == ")": d -= 1
            elif ch == "," and d == 0:
                commas.append(k)
        if len(commas) != 1:
            # malformed; bail
            break
        x = inside[:commas[0]].strip()
        N = inside[commas[0] + 1:].strip()
        replacement = f"ts_mean(abs(subtract({x}, ts_mean({x}, {N}))), {N})"
        e = e[:m.start()] + replacement + e[j:]
    return e


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source", help="Path to runs.md")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--rank-by", choices=("icir", "ic_mean"), default="icir")
    ap.add_argument("--out", default="QML_FACTORS_TRANSLATED.json")
    args = ap.parse_args()

    raw = parse_runs_md(Path(args.source))
    print(f"parsed {len(raw)} rows from {args.source}")

    translatable = [r for r in raw if is_translatable(r["expr"])]
    print(f"  {len(translatable)} factors are translatable (op subset is portable)")

    # Translate, dedup by translated expression.
    seen = set()
    translated: list[dict] = []
    for r in translatable:
        try:
            wq = translate(r["expr"])
        except Exception as e:
            continue
        if wq in seen:
            continue
        seen.add(wq)
        translated.append({**r, "wq_expr": wq})
    print(f"  {len(translated)} unique translated expressions")

    # Rank by absolute icir (or ic_mean): higher = stronger directional signal.
    translated.sort(key=lambda r: abs(r[args.rank_by]), reverse=True)

    # Greedy: pick top-K with structurally distinct skeletons. All-clones
    # of `ts_corr(price, volume, 237)` collapse to one slot.
    from mining_pipeline.extract_uncorrelated import skeleton  # noqa: E402

    picked: list[dict] = []
    used_skeletons: set[str] = set()
    for r in translated:
        # Wrap negative-IC signals with reverse() so the WQ-returned IS
        # Sharpe is positive (a negatively-correlated alpha is just as
        # tradable, but our >1.25 gate is one-sided).
        wq = r["wq_expr"]
        if r["ic_mean"] < 0:
            wq = f"reverse({wq})"
        try:
            sk = skeleton(wq)
        except Exception:
            continue
        if sk in used_skeletons:
            continue
        used_skeletons.add(sk)
        picked.append({**r, "wq_expr_signed": wq, "skeleton": sk})
        if len(picked) >= args.top:
            break
    print(f"  picking top {len(picked)} structurally-distinct (signed) "
          f"by |{args.rank_by}|")
    print()
    for r in picked:
        print(f"  ic={r['ic_mean']:+.4f}  icir={r['icir']:+.4f}  sk={r['skeleton'][:60]}")
        print(f"    Qlib: {r['expr'][:120]}")
        print(f"    WQ  : {r['wq_expr_signed'][:120]}")
        print()

    # Emit in extract_uncorrelated.py / pipeline.py report shape so
    # mining_pipeline.wq_pipeline --from-report can ingest it.
    report = {
        "config": {"source": args.source, "top": args.top,
                   "rank_by": args.rank_by,
                   "translator_notes": "Med->ts_mean (no WQ ts_median); "
                                       "Mad expanded; DownResample wrapper "
                                       "dropped (daily evaluation).",
                   "skipped_ops": sorted(UNSUPPORTED),
                   "skipped_fields": sorted(UNSUPPORTED_FIELDS)},
        "factors": [
            {
                "expression": r["expr"],
                "optimized": r["wq_expr_signed"],
                "wq_expr_raw": r["wq_expr"],
                "skeleton": r["skeleton"],
                "ic_mean": r["ic_mean"],
                "icir": r["icir"],
                "params": {},
            }
            for r in picked
        ],
    }
    Path(args.out).write_text(json.dumps(report, indent=2))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
