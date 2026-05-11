# QuantML port -- final deliverables

Six rounds × five structurally distinct factors = 30 candidate
factors ported from the [QuantML factor zoo](https://github.com/QuantMLResearch/QuantML)
methodology and submitted to WQ Brain `/simulations` under USA TOP3000
with per-factor tuned settings.

**Gate: SH > 1.25 ∧ turnover < 0.25 ∧ fitness > 1.0** (the canonical
threshold from CLAUDE.md).

## Result

> **1 new survivor (QM_R6_01) plus the prior-task survivor OA24 -- two
> viable factors total.**

| factor | SH | TO | FIT | annual ret | drawdown | alpha_id | source |
|--------|---:|---:|---:|---:|---:|---|---|
| **QM_R6_01** body-var-asymmetry | **1.51** | **0.06** | **2.38** | **31%** | 29% | `58Ln2d05` | this task, round 6 |
| **OA24** OHLC-tail-asymmetry | **1.47** | **0.07** | **2.47** | **35%** | 40% | `vR5wxKO3` | prior task, OpenAlpha |

Both factors share a **single structural insight**:

> **Cross-sectional 100-day asymmetric variance: downside half minus
> upside half.** Long names whose negative moves are more variable than
> their positive moves; short the inverse.

They differ in which channel measures the asymmetry: OA24 uses
*low-vs-prior-close* vs *high-vs-prior-close* (overnight + intraday tail);
QM_R6_01 uses the *intraday body* `(close − open)/open` masked by sign.

## Final factor #1 -- QM_R6_01 (delivered today)

```text
expression : ts_std_dev((close - open) / open * less(close - open, 0), 100)
           - ts_std_dev((close - open) / open * greater(close - open, 0), 100)
alpha_id   : 58Ln2d05
settings   : region=USA, universe=TOP3000, delay=1, decay=4,
             neutralization=INDUSTRY, truncation=0.08,
             pasteurization=ON, language=FASTEXPR
```

- IS Sharpe: **1.51**
- IS turnover: **0.0638**  (well under 0.25 cap)
- IS fitness: **2.38**
- IS annualised returns: **30.94 %**
- IS drawdown: 29 %
- WQ checks passed: ~5/8 (LOW_SHARPE / LOW_TURNOVER / etc. all pass)

**Interpretation.** Over a 100-day window the cross-sectional difference
between (i) the std of *down-body intraday returns* (days where
close < open) and (ii) the std of *up-body intraday returns* (close >
open). When a name's down-body variance dominates, the market is over-
discounting its tail risk → it earns a premium → long. When up-body
variance dominates (lottery-like names) → short.

## Final factor #2 -- OA24 (from the prior OpenAlpha task)

```text
expression : ts_std_dev(low  / ts_delay(close, 1) - 1, 100)
           - ts_std_dev(high / ts_delay(close, 1) - 1, 100)
alpha_id   : vR5wxKO3
settings   : same as QM_R6_01 except decay=0
```

Identical *shape* (downside-vs-upside 100d std diff), different
*channel* (overnight+intraday extreme vs intraday body). They are
likely **complementary signals**; combining them via z-sum could push
SH beyond either alone.

## Process and structural ceiling

The 30 candidates broke down by category:

| round | theme | best SH |
|-------|-------|--------:|
| R1 | core QuantML categories (amplitude, median, MAD, kurt, Amihud) | 0.78 |
| R2 | idio-vol, recency, momentum, volume anomaly, skew | 0.84 |
| R3 | tail-asymmetry on returns, vol-of-vol, lottery, composite | 0.75 |
| R4 | OHLC pressure, conditional downvol, overnight gap, z-sum, Bollinger-z | **0.94** |
| R5 | R4_02 tuning, beta, close-vwap, range-volume | 0.83 |
| R6 | OHLC candlestick (body asymmetry, body-range, shadows, range position, signed-power body) | **1.51** ✓ |

**The hard ceiling for return-only factors on USA TOP3000 + industry-
neut + 0.08 truncation is SH ≈ 0.94** (R4_02). To break through,
**OHLC-channel** structures (R6_01, OA24) are required: those expose
intraday-level information that close-to-close returns can't capture.

Three rank-/z-composite attempts (R3_05, R4_04, R5_02) all
**underperformed** their best component, suggesting strong cross-
sectional correlation among the variance-tail shapes.

## Reproducing

```bash
# credentials in repo-root credential.txt (gitignored)
python scripts/submit_quantml_r1.py   # round 1: 5 factors
python scripts/submit_quantml_r2.py   # round 2: 5 factors
python scripts/submit_quantml_r3.py   # round 3
python scripts/submit_quantml_r4.py   # round 4
python scripts/submit_quantml_r5.py   # round 5
python scripts/submit_quantml_r6.py   # round 6 -- produces QM_R6_01
```

All round scripts append to `WQ_QUANTML_RESULTS.json` (30 entries
when complete).
