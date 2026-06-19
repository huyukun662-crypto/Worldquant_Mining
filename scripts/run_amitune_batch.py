"""Push the dense Amihud-illiquidity D0 factor from SH 1.64 -> >=2.0.

Base (ilq_250_100): -zscore(ts_decay_linear(ts_mean((high-low)/(close*vol),
250), 100)) -> SH 1.64, FIT 2.05, TO 0.014, CONCENTRATED_WEIGHT PASS.
Only LOW_SHARPE short. Economics: illiquidity premium (dense, neut NONE).

To reach 2.0 we (a) lengthen the averaging window and (b) add a small
COMPLEMENTARY term that is uncorrelated with both Amihud and the account's
submitted 1Y751gZm (which is Amihud-750/350 + 5/20-day reversal): we use
low-volatility and a 120-day (long-horizon) reversal -- different anomalies
and horizons. Verified later via /check SELF_CORRELATION vs 1Y751gZm.
"""
from scripts.d0_batch import run_batch

ILQ = "divide(subtract(high, low), add(multiply(close, volume), 1))"
def z(x, dl): return f"zscore(ts_decay_linear({x}, {dl}))"

ilq300 = f"-1 * {z(f'ts_mean({ILQ}, 300)', 120)}"
ilq400 = f"-1 * {z(f'ts_mean({ILQ}, 400)', 150)}"
lowv   = f"-1 * {z('ts_std_dev(returns, 60)', 20)}"
ltrev  = f"-1 * {z('ts_av_diff(close, 120)', 60)}"

C = [
 ("ilq400",        ilq400, {"neutralization":"NONE","truncation":0.05,"decay":0}),
 ("ilq300",        ilq300, {"neutralization":"NONE","truncation":0.05,"decay":0}),
 ("ilq300_lowv",   f"add({ilq300}, multiply(0.5, {lowv}))", {"neutralization":"NONE","truncation":0.05,"decay":0}),
 ("ilq300_ltrev",  f"add({ilq300}, multiply(0.5, {ltrev}))", {"neutralization":"NONE","truncation":0.05,"decay":0}),
 ("ilq400_lowv",   f"add({ilq400}, multiply(0.5, {lowv}))", {"neutralization":"NONE","truncation":0.05,"decay":0}),
 ("ilq400_both",   f"add(add({ilq400}, multiply(0.4, {lowv})), multiply(0.4, {ltrev}))", {"neutralization":"NONE","truncation":0.05,"decay":0}),
 ("ilq400_lowv_mkt", f"add({ilq400}, multiply(0.5, {lowv}))", {"neutralization":"MARKET","truncation":0.05,"decay":0}),
]

if __name__ == "__main__":
    run_batch(C, max_workers=2)
