# Delay-0 (D0) factor mining — session findings

Account `2445560398@qq.com` (user `YH61983`), USA TOP3000, delay=0,
IS window 2019-01-01 → 2023-12-31.

## Platform facts established this session

- **delay=0 IS now available** for simulation on this account (the old
  `CLAUDE.md` note "Delay 0 is not available" is stale — `/simulations`
  with `delay:0` returns HTTP 201 and completes normally).
- **Submission bar (from `/alphas/{id}/check`)** on this account — which
  is enrolled in the **IQC2026** competition — is markedly stricter than
  the generic 1.25:
  - `LOW_SHARPE`  limit **2.0**
  - `LOW_FITNESS` limit **1.3**
  - `LOW_TURNOVER` > 0.01, `HIGH_TURNOVER` < 0.7
  - `CONCENTRATED_WEIGHT` (no single-name weight > 0.1 on any date)
  - `LOW_SUB_UNIVERSE_SHARPE` (scales with Sharpe)
  - `SELF_CORRELATION` — computed async, **only vs SUBMITTED alphas**
    (this account has just 1 submitted: a delay-1 PV reversal), so a
    fresh D0 factor self-correlates low regardless of construction.
  - `MATCHES_COMPETITION` (auto for USA TOP3000).
  This 2.0/1.3 bar was confirmed on our OWN freshly-created alphas, not
  just competition-tagged ones.
- **Operator tier**: 67 operators (basic). Notably ABSENT: `ts_skewness`,
  `ts_kurtosis`, `ts_entropy`, `ts_max`, `ts_co_skewness`. Available cold
  ops: `kth_element, ts_arg_max/min, ts_quantile, ts_step, ts_covariance,
  ts_regression, hump, last_diff_value, days_from_last_change`.
- **Throughput**: effective concurrency ≈ 1 delay-0 simulation at a time;
  server-side sims survive client kills, so each ret&relaunch leaves a
  stale sim holding the slot. Budget ~1 completed sim / 3-5 min.
- `signed_power(x, e)` needs a FRACTIONAL exponent (e.g. 0.05-0.5);
  fundamental/analyst fields are sparse at d0 and MUST be `ts_backfill`'d
  or the signal collapses to ~0.
- D0 datasets available (USA TOP3000): fundamental6/2, news12/18,
  analyst4, earnings4 (mostly IV/HV — avoided per "no IV"), option6/8
  (IV — avoided), pv1/pv13, socialmedia8/12 (0 fields at this slice).

## Constraints in tension

The task asks for a D0 factor that is **all of**: fresh / uncorrelated
with prior work, NOT using `news_short_interest` (the account's dominant
dataset), NOT using IV, economically meaningful, concise, regularized —
**and** passing the **SH ≥ 2.0 / FIT ≥ 1.3** competition submit bar.

The account's only proven ≥2.0 D0 alphas come from exactly the two
sources the freshness/uncorrelation constraint rules out:
1. `news_short_interest` composites (SH ≈ 2.0, TO ≈ 0.047), and
2. one heavily hand-tuned 9-term PV+estimate composite `YPpGdMRv`
   (SH 2.08, TO 0.013) using `ts_regression(returns, volume/adv20,…)`,
   `est_epsr`, `est_fcf`, `rel_ret_*`, double `group_neutralize`
   (incl. the `pv13_r2_*` statistical risk model), `vector_neut(returns)`
   and `hump`.

## What was mined and measured (fresh, no short-interest, no IV)

| family | best fresh signal (D0, IS) | SH | TO | note |
|---|---|---:|---:|---|
| PV single (low-vol, reversal, illiq, range) | `-ts_std_dev(returns,22)` etc. | ~0.2 | mid | weak |
| News sentiment (Ravenpack `nws18_*`) | `group_zscore(ts_backfill(vec_avg(nws18_qep),22),subind)` | 0.40 | 0.55 | high turnover, noisy |
| Analyst (analyst4, vec_avg) | coverage `vec_avg(anl4_basicconqf_numest)` | **1.06** | **0.06** | strongest fresh single; very persistent |
| Analyst dispersion | `(high−low)/|mean|` of EPS estimates | 0.90 | 0.08 | persistent |
| Economic-links momentum | `rel_ret_cust+part−comp` | 0.04 | mid | weak this window |
| Fundamental Q-V-I composite | ebit/ev + ebit/assets + cfo/assets − Δassets | 0.12-0.34 | ~0.02 | value dead 2019-23 |
| Wide 10-signal breadth composite | risk-model + subind neut + vneut + hump | ~0.0 | 0.009 | averaging zero-IC signals → 0 |

**Conclusion so far**: across ~35 D0 simulations, no fresh, uncorrelated,
short-interest-free, IV-free signal exceeds **~1.06 Sharpe** — well under
the 2.0 competition submit bar. The 2019-2023 IS window is hostile to the
value/quality/low-vol anomalies, and the genuinely strong D0 alt-data on
this account (`news_short_interest`) is excluded by the freshness rule.

The remaining untested lever is the `ts_regression(returns, volume/adv20,
…, rettype)` price-impact operator (the one operator demonstrably carrying
IC on this account); a rettype sweep + fresh composite around it is in
progress. Even so, reaching a clean fresh 2.0 looks unlikely without
leaning on the proven `est_*`/`rel_ret`/risk-model machinery, which would
reduce novelty.

## Update 2: short_interest authorized — concentration is the wall

The user authorized `news_short_interest`. Best fresh construction:
`fresh_ey` (zq9zQ391) =
`signed_power(winsorize(add(group_zscore(ts_backfill(news_short_interest,44),
subindustry), multiply(0.3, zscore(ts_backfill(divide(ebit,
enterprise_value),22)))), std=4), 0.05)`
-> **SH 2.07, FIT 3.27, TO 0.091**, neut SUBINDUSTRY, delay 0.
`/check`: passes LOW_SHARPE(2.0), LOW_FITNESS(1.3), turnover, sub-universe;
**FAILS CONCENTRATED_WEIGHT** (0.5 on 2021-06-07, limit 0.1).

CONCENTRATED_WEIGHT is **structural** to news_short_interest: the field is
sparse (bi-monthly, partial coverage). On 2021-06-07 only a few names have
data -> after neutralization one name gets 50% of the book. This is why
ALL 70+ news_short_interest alphas on this account FAIL CONCENTRATED_WEIGHT
and remain UNSUBMITTED. Verified unfixable while keeping SH:
  - lower truncation (0.02): no change (CW computed on neutralized weights)
  - ts_decay_linear / decay=40: no change (not a one-day spike)
  - nanHandling ON: no change
  - longer ts_backfill (250): CW unchanged, SH collapses (stale)
  - if_else(is_nan->0) + dense term: CW PASSES but SH collapses to ~1.1
    (the SH *is* the concentration in covered names).

## Update 3: dense Amihud is the submittable archetype, caps ~1.7

The account's only SUBMITTED D0 alpha (1Y751gZm, SH 2.05, all checks pass)
is dense PV, neut NONE: Amihud illiquidity (high-low)/(close*volume) over
750d + 5/20d reversal. Dense -> CONCENTRATED_WEIGHT passes.

Fresh dense Amihud (different windows) passes ALL checks except LOW_SHARPE:
  - `-zscore(ts_decay_linear(ts_mean((H-L)/(C*V),250),100))` -> SH 1.57
  - `-zscore(ts_decay_linear(ts_mean((H-L)/(C*V),500),200))` -> SH 1.64
  - + 0.5*nan-safe short_interest tilt (ami_si05) -> **SH 1.71** (best dense)
  - higher SI weight (1.5) -> SH drops to 1.36 (nan->0 dilutes the base)

So the dense (CONCENTRATED_WEIGHT-passing) ceiling for FRESH signals in this
period is ~1.7, while concentrated short_interest reaches 2.07 but fails
CONCENTRATED_WEIGHT. The two binding submit checks (LOW_SHARPE>=2.0 AND
CONCENTRATED_WEIGHT) are in direct tension for fresh signals.

Remaining lever (in test): replicate the PROVEN dense 2.0 recipe
(Amihud-750 + reversal, like 1Y751gZm) with different windows + a low-vol
term for distinctiveness -> dense (CW pass) AND SH~2.0. Self-correlation vs
the submitted 1Y751gZm is evaluated only at competition close (PENDING now),
so cannot be confirmed this session.
