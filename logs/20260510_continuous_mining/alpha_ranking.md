# Alpha Ranking — Continuous Mining Round

Stage 5 / Agent 5 — Evaluator & Recorder.

## Mining loop

Continuous miner ran across 700 candidate base-expressions (22.8 min wall) drawn from 37 curated mechanism-family templates plus an unbounded random-expression generator. Each candidate was Optuna-tuned over its integer literals (40 trials, IS Sharpe with turnover-cap penalty as the objective) on the 251-name yfinance proxy.

The miner stops on **N structurally distinct survivors** of the strict gates `IS_SH > 1.25 ∧ IS_TO < 0.25 ∧ OS_SH ≥ IS_SH`. Two candidates with the same operator skeleton (differing only in window values) share a structural signature and count as **one** distinct survivor.

## Selected: top 4 by IS Sharpe

| rank | IS_SH | IS_TO | OS_SH | OS_TO | expression |
|-----:|------:|------:|------:|------:|------------|
| 1 | +1.319 | 0.007 | +1.803 | 0.007 | `zscore(ts_mean(ts_std_dev(subtract(vwap, volume), 16), 45))` |
| 2 | +1.293 | 0.016 | +1.667 | 0.018 | `zscore(ts_mean(ts_std_dev(divide(adv20, high), 33), 3))` |
| 3 | +1.280 | 0.006 | +1.754 | 0.006 | `scale(ts_decay_linear(ts_std_dev(add(vwap, volume), 45), 33))` |
| 4 | +1.257 | 0.003 | +1.813 | 0.002 | `scale(ts_decay_linear(ts_decay_linear(add(volume, high), 42), 46))` |

## Floor checks (local proxy)

- [x] Local IS_SH > 1.25 — passed by all 4.
- [x] Local IS_TO < 0.25 — passed by all 4.
- [x] Local OS_SH ≥ IS_SH — passed by all 4.
- [x] Structurally distinct (≠ operator skeleton) — verified.
- [ ] WQ Brain `IS_SH > 1.25 ∧ IS_TO < 0.25 ∧ OS_SH ≥ IS_SH` — pending submission.

## Decision

**PROCEED-TO-SUBMISSION.** All 4 selected pass the local strict gates and are structurally distinct. Submit `submission_payload.json` to WQ Brain via `scripts/submit_alpha.py` for authoritative validation. Per CLAUDE.md the local 251-name proxy is noisy and prior local-strict survivors have scored poorly on WQ Brain, so the 4 here should be re-ranked by WQ `/alphas/{id}.is.sharpe` after submission.

## Falsification question

> If this ranking is wrong by 50%, what is the most likely single cause?

Most likely cause: **survivorship-bias-by-search**. Optuna with 40 trials per expression overfits the IS window to a small basin in window-space; the OS_SH ≥ IS_SH filter is the local guard, but the OS window itself is only 590 days (2024-01-01 → 2026-05-08), so a regime that favors the selected mechanism in 2024-2026 will look like out-of-sample stability. Counter-test: WQ Brain's TVT methodology and the IS window 2019-2023 with separate validation slices per `tvt-split-template.md`.
