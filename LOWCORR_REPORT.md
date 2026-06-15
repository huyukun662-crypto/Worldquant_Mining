# Low-correlation factor mining — final report

Account `Shu476891497@gmail.com` (id `XS45327`), USA / TOP3000 / **delay=1**,
**no IV fields**, submittable-oriented, low turnover + low max drawdown.

## Campaign summary

| run | archetype source | trials | unique submittable | best Sharpe |
|----|------------------|-------:|-------------------:|------------:|
| v1 | leverage + PV (windows 2-15) | 56 | 0 | 1.35 (TO 0.40 > cap) |
| **v2** | **leverage + orthogonal combos, high decay** | 50 | **7** ✅ | **1.69** |
| v3 | diverse non-leverage fundamentals | 50 | 0 | 0.89 |
| v4 | events/sentiment (analyst/news, orthogonal) | 45 | 0 | 0.45 |

**Conclusion.** On this account at delay=1 under the low-turnover constraint
(TO < 0.25), **only the leverage family** (`debt`/`liabilities`-to-`assets`)
clears the `LOW_SHARPE` (≥1.25) and `LOW_FITNESS` (≥1.0) gates. Economically
orthogonal families — diverse fundamentals (ROA/ROE, value, growth, margins,
accruals, momentum, low-vol) and event/sentiment signals (analyst EPS
revisions, earnings surprise / PEAD, target/recommendation changes, news
sentiment) — top out at Sharpe 0.45-0.89 and never reach the gates. This is
the WQ fitness identity at work: `fitness = sharpe·√(|ret|/max(TO,0.125))`,
so a low-turnover signal must have an unusually high Sharpe to clear
fitness ≥ 1.0, and only leverage does on this universe.

Therefore **no NEW low-correlation _submittable_ factor exists** under the
low-turnover constraint here. To get genuinely orthogonal submittable alphas
you must relax turnover (e.g. the v1 `vol_scaled_reversal` reached Sharpe
1.35 — orthogonal to leverage — at TO ≈ 0.40), which the user chose not to do.

## PnL correlation of the 7 submittable (v2) alphas

Daily-PnL Pearson correlation (IS 2019-2023, 1236 days):

```
            gJ3LjoP KPLZOpW qMXVNNl QPQ6NLO ZYoNg9x mLXQgpA 0m85GPq
gJ3LjoPM     1.00    0.85    0.64    0.78    0.73    0.78    0.86
KPLZOpWz     0.85    1.00    0.52    0.94    0.90    0.92    0.68
qMXVNNlO     0.64    0.52    1.00    0.40    0.32    0.42    0.66   <- decorrelated outlier
QPQ6NLOg     0.78    0.94    0.40    1.00    0.96    0.98    0.58
ZYoNg9xj     0.73    0.90    0.32    0.96    1.00    0.98    0.52
mLXQgpAW     0.78    0.92    0.42    0.98    0.98    1.00    0.58
0m85GPq2     0.86    0.68    0.66    0.58    0.52    0.58    1.00
```

The debt-based ratios are near-identical (0.9-0.98). `qMXVNNlO`
(`liabilities_curr/assets`, current-liabilities leverage) is the only member
that decorrelates from the debt cluster (0.32-0.42). The maximum mutually
`|corr| < 0.5` basket from the submittable set therefore has **2** factors.

## Recommended low-correlation submittable baskets

**Best 2-factor orthogonal basket (both submittable, |corr| = 0.32):**

1. `qMXVNNlO` — `rank(divide(liabilities_curr, assets))`
   - SH 1.53 · TO 0.016 · FIT 1.17 · DD 0.047
   - USA · TOP3000 · delay=1 · SUBINDUSTRY · decay=128 · truncation=0.02 · pasteurization=ON
2. `ZYoNg9xj` — `rank(divide(debt_lt, assets))`
   - SH 1.40 · TO 0.017 · FIT 1.19 · DD 0.064
   - USA · TOP3000 · delay=1 · SUBINDUSTRY · decay=32 · truncation=0.05 · pasteurization=ON

**Highest-quality single (correlates with everything, so use alone):**

- `gJ3LjoPM` — `add(zscore(rank(divide(liabilities, assets))), zscore(rank(ts_delta(divide(income, cap), 43))))`
   - SH 1.69 · TO 0.029 · FIT 1.52 · DD 0.075
   - USA · TOP3000 · delay=1 · SUBINDUSTRY · decay=128 · truncation=0.02 · pasteurization=ON

Common fixed settings: `language=FASTEXPR · unitHandling=VERIFY ·
nanHandling=OFF · instrumentType=EQUITY · maxTrade=OFF · testPeriod=P0Y0M`.

## Artifacts
- `WQ_SUBMITTABLE_CANDIDATES_v2.json` — 7 submittable leverage alphas (full settings)
- `WQ_LOWCORR_CANDIDATES.json` / `_all.json` — PnL-correlation selection output
- `WQ_AGENT_REPORT_v{2,3,4}.json` — every trial with full `checks`
- `scripts/lowcorr_select.py` — PnL-correlation basket selector

## v5 update — orthogonal reversal sleeve (turnover cap relaxed to 0.40)

After the leverage family was submitted, new factors must avoid leverage
(else SELF_CORRELATION rejects them). v5 mined non-leverage reversal /
momentum / volume signals with `--turnover-cap 0.40`.

Result: 45 trials, **0 fully-submittable**, but the best near-miss is a
genuinely orthogonal, high-Sharpe, low-drawdown signal:

- `kqK6ZoXK` — `reverse(rank(divide(subtract(close, low), subtract(high, low))))`
  (close-location-in-range reversal)
  - SH 1.57 · TO 0.427 · FIT 0.82 · DD 0.064
  - USA · TOP3000 · delay=1 · (settings in WQ_AGENT_REPORT_v5.json)
  - Passes every IS check EXCEPT **LOW_FITNESS** (0.82 < 1.0). Fails only
    because turnover (0.427) sits in the fitness denominator
    (`fitness = sharpe·√(|ret|/max(TO,0.125))`).

PnL correlation vs the submitted leverage family (max over the 7):

| candidate | max \|corr\| vs leverage | mean | SH | DD |
|---|---:|---:|---:|---:|
| `kqK6ZoXK` | 0.28 | 0.21 | 1.57 | 0.064 |
| `A138NAqd` | 0.26 | 0.19 | 1.20 | 0.088 |
| `zqWn3LpX` | 0.24 | 0.16 | 1.40 | 0.064 |

→ These reversals ARE orthogonal to leverage (|corr| ≤ 0.28). They are one
shared signal among themselves (0.83-0.97). The blocker is purely the
fitness gate, which the high-turnover reversal cannot clear.

### Final assessment
- If the target competition treats **LOW_FITNESS as a hard submit gate**:
  no orthogonal submittable factor exists on this universe — leverage is the
  only family that clears fitness ≥ 1.0 (its ultra-low turnover hits the
  0.125 fitness-floor). Best orthogonal *near-miss* = `kqK6ZoXK`.
- If LOW_FITNESS is **not** a hard gate (only LOW_SHARPE + turnover +
  self-correlation bind): `kqK6ZoXK` is a strong submittable factor —
  SH 1.57, DD 0.064, and |corr| 0.28 to the submitted leverage pool.

## v6 result — SUBMITTABLE orthogonal factors (fitness gate crossed)

v6 wrapped the orthogonal close-loc-in-range reversal in `ts_decay_linear`
(cutting turnover from 0.43 to ~0.10, which lifts fitness) and blended it
with a slow `asset_turnover` leg. **2 fully-submittable factors** result —
every IS check passes (SH ≥ 1.25, FIT ≥ 1.0, turnover/concentration/
sub-universe), with low turnover and low drawdown:

| alpha_id | SH | TO | FIT | DD | ret | corr vs leverage |
|---|---:|---:|---:|---:|---:|---:|
| `E5KP2XaJ` | 1.31 | 0.121 | 1.26 | 0.099 | 0.115 | **0.43** ✅ |
| `QPQpAd7Q` | 1.43 | 0.091 | 1.27 | 0.080 | 0.098 | 0.50 (borderline) |

**`E5KP2XaJ`** — recommended NEW orthogonal submittable factor
```
add(zscore(reverse(rank(ts_decay_linear(divide(subtract(close, low), subtract(high, low)), 8)))),
    zscore(rank(divide(sales, assets))))
```
`USA · TOP3000 · delay=1 · SECTOR · decay=16 · truncation=0.08 · pasteurization=ON`

**`QPQpAd7Q`** — higher Sharpe but borderline self-correlation (0.50)
```
add(zscore(reverse(rank(ts_decay_linear(divide(subtract(close, low), subtract(high, low)), 5)))),
    zscore(rank(divide(sales, assets))))
```
`USA · TOP3000 · delay=1 · INDUSTRY · decay=32 · truncation=0.08 · pasteurization=ON`

The two are 0.90 correlated with each other (same archetype) — submit ONE.
The `asset_turnover` (sales/assets) leg lifts fitness over 1.0 but shares the
`assets` denominator with leverage, raising correlation from the pure
reversal's 0.28 to 0.43-0.50. Purer-PV blends (reversal + low-vol / momentum)
stayed more orthogonal but did not clear the fitness gate.

### Achievable frontier (orthogonality vs submittability)
- Most orthogonal submittable: **`E5KP2XaJ`** (corr 0.43, SH 1.31, FIT 1.26).
- Most orthogonal overall: `kqK6ZoXK` (corr 0.28) — not submittable (FIT 0.82).
