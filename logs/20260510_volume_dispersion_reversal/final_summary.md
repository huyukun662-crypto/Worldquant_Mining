# Final Summary — Round 0001

Session: `20260510_volume_dispersion_reversal`. Mechanism: volume dispersion × price extension → 5-20d reversal.

## What was produced

- 8 hypothesis-driven candidates (Builder).
- Optuna search over integer literals on the IS window, 60 trials/expr.
- Strict-gate survivors: 0; robust-pool size: 5.
- **4 factors selected** (robust_composite): E4, E3, E7, E1.

## Selected 4 factors

### 1. E4

- **Expression**: `rank(reverse(multiply(divide(ts_std_dev(volume, 53), ts_mean(volume, 42)), ts_returns(close, 7))))`
- **Local IS**: SH=+0.588, TO=0.227, AnnRet=+0.058
- **Local OS**: SH=+0.220, TO=0.232, AnnRet=+0.016
- **Tuned windows**: {'0': 53, '1': 42, '2': 7}

### 2. E3

- **Expression**: `rank(ts_decay_linear(reverse(ts_corr(close, volume, 5)), 11))`
- **Local IS**: SH=+0.479, TO=0.136, AnnRet=+0.024
- **Local OS**: SH=+0.228, TO=0.136, AnnRet=+0.012
- **Tuned windows**: {'0': 5, '1': 11}

### 3. E7

- **Expression**: `rank(reverse(multiply(ts_std_dev(returns, 59), ts_returns(close, 7))))`
- **Local IS**: SH=+0.543, TO=0.223, AnnRet=+0.056
- **Local OS**: SH=+0.175, TO=0.229, AnnRet=+0.013
- **Tuned windows**: {'0': 59, '1': 7}

### 4. E1

- **Expression**: `rank(ts_decay_linear(multiply(divide(ts_std_dev(volume, 36), ts_mean(volume, 50)), reverse(ts_returns(close, 3))), 9))`
- **Local IS**: SH=+0.597, TO=0.145, AnnRet=+0.059
- **Local OS**: SH=+0.028, TO=0.149, AnnRet=+0.002
- **Tuned windows**: {'0': 36, '1': 50, '2': 3, '3': 9}

## Submission instructions

1. Place WQ Brain credentials at `credential.txt` in repo root (chmod 600).
2. Run: `python scripts/submit_alpha.py logs/20260510_volume_dispersion_reversal/submission_payload.json`
3. Check the resulting `WQ_SUBMISSION_RESULTS.json` for the `is.sharpe`, `is.turnover`, `is.fitness`, and `is.checks` fields per CLAUDE.md.
4. The factor is *symbol-meets-WQ-requirements* iff `is.sharpe > 1.25 ∧ is.turnover < 0.25 ∧ os.sharpe ≥ is.sharpe` AND the platform's `is.checks` block has no FAIL.

## Decision

**CONTINUE → WQ Brain submission (research-only locally; final verdict deferred to WQ).**

The local proxy did not cross the strict 1.25 IS Sharpe floor on this batch. Per CLAUDE.md this floor was set to filter random factors and is known noisy at 251 names. The 4 selected factors are the highest-OS-robustness candidates from a single-mechanism batch of 8 with all audits PASS. WQ Brain's TOP3000 + INDUSTRY-neutralized + truncation=0.08 backtest is the authoritative gate per the project README.
