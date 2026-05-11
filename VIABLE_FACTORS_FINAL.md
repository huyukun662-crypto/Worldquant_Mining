# Final viable factors -- delivery

Eleven rounds × 5 factors = 55 candidate QuantML-port factors plus
34 OpenAlpha-port factors = **89 submitted to WQ Brain**.

**Gate**: `SH > 1.35` ∧ `turnover < 0.15` ∧ `fitness > 1.0`.

## Three structurally distinct viable factors

| # | factor | shape family | SH | TO | FIT | ann.ret | dd | alpha_id |
|---|--------|--------------|---:|---:|---:|---:|---:|----------|
| 1 | **QM_R6_01** body var asymmetry | variance asym (OHLC) | **1.51** | **0.06** | **2.38** | 31% | 29% | `58Ln2d05` |
| 2 | **OA24** OHLC tail asymmetry | variance asym (OHLC) | **1.47** | **0.07** | **2.47** | 35% | 40% | `vR5wxKO3` |
| 3 | **QM_R8_03** session decomposition | mean diff (sessions) | **1.50** | **0.10** | **1.80** | 18% | — | `O0nOQGJb` |

Plus a near-duplicate of #3:
| 4 | QM_R11_05 peer-residualised session | mean diff (sessions, peer-rel) | 1.49 | 0.10 | 1.81 | 18% | — | `WjNMm87o` |

R11_05's IS Sharpe / turnover / sub-universe Sharpe match R8_03 to two
decimal places (`SH 1.49 vs 1.50`, `TO 0.0961 vs 0.0968`, `Sub-SH 1.29
vs 1.27`) -- essentially the same factor with the sub-industry mean
explicitly stripped. Not a structurally independent signal.

## Factor 1 -- QM_R6_01 (body variance asymmetry)

```
expression:
  ts_std_dev((close - open) / open * less(close - open, 0), 100)
  - ts_std_dev((close - open) / open * greater(close - open, 0), 100)

settings:
  region=USA, universe=TOP3000, delay=1, decay=4,
  neutralization=INDUSTRY, truncation=0.08,
  pasteurization=ON, language=FASTEXPR
```

100-day cross-sectional asymmetric variance of the intraday body
`(close - open) / open`. Long names whose down-body days
(`close < open`) have more variable returns than their up-body days.

## Factor 2 -- OA24 (OHLC tail asymmetry)

```
expression:
  ts_std_dev(low  / ts_delay(close, 1) - 1, 100)
  - ts_std_dev(high / ts_delay(close, 1) - 1, 100)

settings:  same as QM_R6_01 except decay=0
```

100-day std of (today's low / yesterday's close) - std of (today's
high / yesterday's close). Same shape as QM_R6_01, different price
channel: extreme prices vs prior close, not intraday body.

## Factor 3 -- QM_R8_03 (overnight − intraday decomposition)

```
expression:
  ts_mean(open / ts_delay(close, 1) - 1, 60)
  - ts_mean(close / open - 1, 60)

settings:
  region=USA, universe=TOP3000, delay=1, decay=4,
  neutralization=SUBINDUSTRY, truncation=0.05,
  pasteurization=ON, language=FASTEXPR
```

Difference between 60-day mean overnight return and 60-day mean
intraday return. Captures the well-known **overnight premium /
intraday drift** decomposition: long names whose gap-up bias exceeds
their intraday drift. Mathematically distinct from #1/#2 (mean
diff, not variance asymmetry).

## Correlation rationale (qualitative)

- **#1 and #2 (variance-asym family)** share the same `std(x*less,N) - std(x*greater,N)` shape and both live in OHLC; expected cross-sectional correlation **moderate-to-high** (both proxy the downside-vs-upside tail-asym premium).
- **#3 (session-decomp family)** is a `mean(overnight) − mean(intraday)` shape with no variance terms; expected correlation with #1/#2 is **low**.

WQ Brain's own `SELF_CORRELATION` check is still PENDING for all four submissions and would give the authoritative numbers; the qualitative argument above is the best available now.

## Empirical findings (89 submissions)

- **Return-only factors cap at SH ≈ 0.94** on USA TOP3000 / INDUSTRY-neut / 0.08 truncation. Confirmed by R4_02 (asym variance on `returns`) → 0.94, R2_05 (skew on `returns`) → 0.84, R1_04 (kurtosis on `returns`) → 0.78.
- **Breaking SH = 1.25 requires OHLC channel information** -- intraday extremes, body, or session prices. Confirmed by R6_01 (body, SH=1.51) and OA24 (OHLC tail, SH=1.47).
- **Session decomposition is the only non-variance shape** that broke the gate (R8_03, SH=1.50). All other shapes attempted (auto-correlation, CV, sign-streak, rank-reversal, volume-shock, Sortino, Sharpe-ratio, regime-vol-ratio, peer-relative momentum, vol-managed return) topped out below SH=1.1.
- **Composites (rank average / z-sum)** of strong singletons consistently UNDERPERFORMED their best component (R3_05, R4_04, R5_02): the underlying variance-asymmetry signals are too correlated cross-sectionally.

## Reproducing

```bash
echo '["<wq-username>","<wq-password>"]' > credential.txt && chmod 600 credential.txt

# OpenAlpha port (produces OA24)
python scripts/submit_openalpha.py

# QuantML port (rounds 1-11; produces QM_R6_01 in round 6, QM_R8_03 in round 8, QM_R11_05 in round 11)
for i in 1 2 3 4 5 6 7 8 9 10 11; do
  python scripts/submit_quantml_r${i}.py
done
```

Results are written incrementally to `WQ_QUANTML_RESULTS.json`
(55 entries) and `WQ_OPENALPHA_RESULTS.json` (34 entries).
