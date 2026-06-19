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
