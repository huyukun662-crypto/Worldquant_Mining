Wrapper x neutralization sweep on seed r2_volwt_decay20.
Core: reverse(ts_decay_linear(multiply(ts_zscore(returns, 5), log(add(divide(volume, adv20), 1))), 20))
Filter: SH>1.25, FIT>1.0, TO<0.25.
