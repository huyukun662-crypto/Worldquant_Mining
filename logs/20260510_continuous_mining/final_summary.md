# Final Summary — Continuous Mining Round

Session: `20260510_continuous_mining`. Goal: 4 structurally distinct alphas passing strict local gates.

## Mining stats

- Candidates evaluated: **700**
- Wall time: **22.8 min**
- Distinct survivors accumulated: **4** (target: 4)

## Selected 4 alphas

### 1. IS_SH=+1.319, OS_SH=+1.803

- **Expression**: `zscore(ts_mean(ts_std_dev(subtract(vwap, volume), 16), 45))`
- **Structural signature**: `zscore(ts_mean(ts_std_dev(subtract(vwap,volume),_),_))`
- **Local IS**: SH=+1.319, TO=0.007, AnnRet=+0.136
- **Local OS**: SH=+1.803, TO=0.007, AnnRet=+0.172
- **Tuned windows**: {'0': 16, '1': 45}

### 2. IS_SH=+1.293, OS_SH=+1.667

- **Expression**: `zscore(ts_mean(ts_std_dev(divide(adv20, high), 33), 3))`
- **Structural signature**: `zscore(ts_mean(ts_std_dev(divide(adv20,high),_),_))`
- **Local IS**: SH=+1.293, TO=0.016, AnnRet=+0.144
- **Local OS**: SH=+1.667, TO=0.018, AnnRet=+0.174
- **Tuned windows**: {'0': 33, '1': 3}

### 3. IS_SH=+1.280, OS_SH=+1.754

- **Expression**: `scale(ts_decay_linear(ts_std_dev(add(vwap, volume), 45), 33))`
- **Structural signature**: `scale(ts_decay_linear(ts_std_dev(add(vwap,volume),_),_))`
- **Local IS**: SH=+1.280, TO=0.006, AnnRet=+0.132
- **Local OS**: SH=+1.754, TO=0.006, AnnRet=+0.169
- **Tuned windows**: {'0': 45, '1': 33}

### 4. IS_SH=+1.257, OS_SH=+1.813

- **Expression**: `scale(ts_decay_linear(ts_decay_linear(add(volume, high), 42), 46))`
- **Structural signature**: `scale(ts_decay_linear(ts_decay_linear(add(volume,high),_),_))`
- **Local IS**: SH=+1.257, TO=0.003, AnnRet=+0.132
- **Local OS**: SH=+1.813, TO=0.002, AnnRet=+0.192
- **Tuned windows**: {'0': 42, '1': 46}

## Submission

```
python scripts/submit_alpha.py logs/20260510_continuous_mining/submission_payload.json
```

Requires `credential.txt` in repo root (chmod 600). Outputs to `WQ_SUBMISSION_RESULTS.json`. The factors qualify per WQ requirements iff the platform's `is.sharpe > 1.25 ∧ is.turnover < 0.25 ∧ os.sharpe ≥ is.sharpe` AND `is.checks` has no FAIL.
