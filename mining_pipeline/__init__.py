"""Mining pipeline package.

Self-contained alpha mining — does NOT reuse any expression from
`worldquant_mining/factor_templates.py` (Alpha101 / classical factors).
Factors are *generated from scratch* by `expressions.py` using random
combinations of canonical operators × PV data fields, then refined by
hyperparameter search.

Pipeline:

    expressions.py  -> generate N random factor expressions (lookback HPs left free)
    evaluator.py    -> evaluate one expression on the OHLCV panel
    backtest.py     -> compute long-short Sharpe + turnover for a factor signal
    screen.py       -> initial filter: IS Sharpe > 1.25 AND turnover < 0.25
    search.py       -> Bayesian (optuna) or grid HP search per surviving expression
    pipeline.py     -> end-to-end: generate -> screen -> HP search -> OOS check
"""
