# US-Stock Factor Mining — Final Results

11 mining rounds through the WorldQuant Brain API on USA TOP3000.
Hard gate (per the user's brief):

```
IS Sharpe   > 1.25
IS Turnover < 0.25
IS window   = 2019-01-01 .. 2023-12-31
```

## Five structurally-distinct PASSing architectures

All wrapped in `group_neutralize(..., subindustry)` (or `industry` for #6).

| # | Architecture | Sharpe | Turn | Fitness | Origin |
|--:|---|---:|---:|---:|---|
| 1 | **TS rank reversal** &nbsp; `ts_decay_linear(-ts_rank(returns, 252), 60)` | +1.620 | 0.235 | +1.290 | R3 |
| 2 | **TS zscore reversal** &nbsp; `ts_decay_linear(-ts_zscore(returns, 252), 60)` | +1.300 | 0.214 | +1.030 | R5 |
| 3 | **Cap-stratified rank** &nbsp; `trade_when(rank(cap)>0.5, ts_decay_linear(-ts_rank(returns,144),40), 0)` | +1.300 | 0.238 | +0.750 | R3 |
| 4 | **Additive composite (rank + zscore)** &nbsp; `ts_decay_linear(-ts_rank(returns,252) - ts_zscore(returns,252), 60)` | +1.380 | 0.223 | +1.100 | R11 |
| 5 | 🥇 **Barbell extreme-decile** &nbsp; `ts_decay_linear(if_else(ts_rank(returns,252)>0.85, -1, if_else(ts_rank(returns,252)<0.15, 1, 0)), 60)` | **+1.700** | **0.213** | **+1.340** | R11 |
| 6 | *(borderline — parametric variant of #1)* &nbsp; same inner alpha, `industry` neutralisation | +1.470 | 0.236 | +1.200 | R11 |

## WQ Brain platform-side checks (alpha #1, alpha_id `88awmEQV`)

```
LOW_SHARPE             PASS  (1.62 > 1.25)
LOW_FITNESS            PASS  (1.29 > 1.0)
HIGH_TURNOVER          PASS  (0.2346 < 0.7)
CONCENTRATED_WEIGHT    PASS
LOW_SUB_UNIVERSE_SHARPE PASS  (1.05 > 0.7)
MATCHES_COMPETITION    PASS  ← Challenge + IQC2026 Stage 1
SELF_CORRELATION       PENDING (computed after platform submission)
```

The alpha is officially flagged for the **International Quant Championship
2026 Stage 1** competition by WQ Brain.

## Round-by-round summary

| Round | Pool | Tested | Passes | Notes |
|--:|---|--:|--:|---|
| Stage-1 (novel) | 30 alphas across 8 categories, defensive | 30 | 0 | best Sharpe 0.6 |
| Round 2 | smoothed reversal core × decay sweep | 20 | 0 | top 1.57 / 0.32 (over-turn) |
| Round 3 | heavy decay, hump, quality-gated, cap-stratified | 20 | 3 | first wins |
| Round 4 | L1 × L2 lookback grid on R3 winner | ~14 (cancelled) | 3 | found L1=120/L2=80 with turn 0.213 |
| Round 5 | 4 structurally-distinct families | 4 | 1 | TS-zscore reversal works |
| Round 6 | Factor-Zoo workflow, 4 categories | 4 | 0 | non-reversal categories collapse |
| Round 7 | reversal × novel weights | 4 | 0 | weight multiplications kill signal |
| Round 8 | new architectures (cumulative, 12m, residual) | 4 | 0 | best 1.06 / 0.06 |
| Round 9 | chase R8-1 + low-vol + variants | 4 | 0 | cumulative-reversal caps at 1.06 |
| Round 10 | intraday/overnight/range/downside inputs | 4 | 0 | three returned zeros |
| Round 11 | composite, daily-rank, barbell, industry-neut | 4 | 3 | barbell is new high (1.700) |
| **Total** | | **108** | **5** distinct + 1 variant | |

## Pipeline architecture

```
generation_two/
├── mine_us_factors.py      ─ Stage-1 screener (3 slots saturated)
│                              pools: novel / round2 / round3 / round4
│                                     round5 / round6 / round7 / round8
│                                     round9 / round10 / round11
├── bayesian_tune.py        ─ Stage-2 GP-Bayesian hyper-parameter tuner
│                              ($-placeholder integer search via skopt)
├── tune_settings.py        ─ Stage-2.5 settings-grid tuner
│                              delay × decay × truncation × universe
│                              × neutralisation
├── os_validate.py          ─ OS sanity check (IS API caches → uses
│                              alpha record’s `os` field; computed
│                              after platform submission)
├── smoke_test.py           ─ auth + 2-alpha sanity check
└── ollama/claude_static_manager.py
                            ─ Ollama drop-in replacement
                              (no local LLM needed)
```

## Key findings

1. **Subindustry-neutralised raw-returns reversal is the only family
   that consistently passes Sharpe > 1.25 in this universe.** Pure
   non-reversal categories (low-vol, quality, sentiment, vol-skew,
   drawdown, B/P momentum) all fall short.
2. **Cumulative aggregations cap around Sharpe 1.06** — even with the
   best lookback / decay combination, `-ts_rank(ts_sum(returns, n), L)`
   smoothed never reaches 1.25.
3. **Heavy `ts_decay_linear` smoothing (window 60+) is what brings
   turnover below 0.25** while preserving most of the Sharpe.
4. **Barbell discrete signals** (long bottom decile / short top decile,
   zero in the middle) outperform continuous rank — Sharpe +1.70 vs
   +1.62 on the same input.
5. **WQ Brain de-duplicates simulations** by `(template + non-date
   settings)` — re-submitting the same template with different
   `startDate`/`endDate` returns the cached alpha. True OS metrics
   require platform submission.

## Reproducing

```bash
cd generation_two
pip install -r requirements.txt scikit-optimize

# Put your WQ Brain credentials in credential.txt (gitignored)
echo 'your-email@example.com'  > credential.txt
echo 'your-password'           >> credential.txt

# Stage-1 screen
python -m generation_two.mine_us_factors --pool round11

# Stage-2 Bayesian fine-tune
python -m generation_two.bayesian_tune \
    --template 'ts_decay_linear(-ts_rank(returns, $L1), $L2)' \
    --space 'L1=120,144,170,200,252,300 L2=40,50,60,80'

# Stage-2.5 settings grid
python -m generation_two.tune_settings \
    --expr 'group_neutralize(ts_decay_linear(-ts_rank(returns, 252), 60), subindustry)'
```

[https://claude.ai/code/session_01Lu4Tz8bG7WPVS6PdVf6jG2](https://claude.ai/code/session_01Lu4Tz8bG7WPVS6PdVf6jG2)
