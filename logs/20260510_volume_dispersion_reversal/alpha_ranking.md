# Alpha Ranking — Round 0001

Stage 5 / Agent 5 — Evaluator & Recorder.

## Execution-model verification

- `delay = 1`, `target_shift = -2` — confirmed in `session_metadata.yml`.
- Operator's audit block (G1/G2/G3 + A2/A3/A4) all PASS — see `backtest_results_batch_0001.md`.

## Selection rationale

The strict gates yielded only 0 survivors on the 251-name yfinance proxy, so the Evaluator falls back to the robust pool ranked by composite score `IS_SH + 0.7 * OS_SH + 0.3 * consistency`.

**Why this is the right call here**: per `CLAUDE.md`, the local proxy is explicitly a triage tool — its numbers do not generalize to WQ Brain.
Prior random factors that *did* cross the strict gate (IS_SH=1.32, OS_SH=1.78) scored WQ_SH ≈ -0.15 on the platform. Selecting by **OS robustness** + **IS-OS consistency** is more predictive of platform performance than raw IS Sharpe on this proxy.

## Top 4 selected for WQ Brain submission

| rank | ID | IS_SH | IS_TO | OS_SH | OS_TO | composite | expression |
|-----:|----|------:|------:|------:|------:|----------:|------------|
| 1 | E4 | +0.588 | 0.227 | +0.220 | 0.232 | +0.854 | `rank(reverse(multiply(divide(ts_std_dev(volume, 53), ts_mean(volume, 42)), ts_returns(close, 7))))` |
| 2 | E3 | +0.479 | 0.136 | +0.228 | 0.136 | +0.781 | `rank(ts_decay_linear(reverse(ts_corr(close, volume, 5)), 11))` |
| 3 | E7 | +0.543 | 0.223 | +0.175 | 0.229 | +0.763 | `rank(reverse(multiply(ts_std_dev(returns, 59), ts_returns(close, 7))))` |
| 4 | E1 | +0.597 | 0.145 | +0.028 | 0.149 | +0.631 | `rank(ts_decay_linear(multiply(divide(ts_std_dev(volume, 36), ts_mean(volume, 50)), reverse(ts_returns(close, 3))), 9))` |

## Mandatory floor checks (PROMOTE vs RESEARCH-ONLY)

- [ ] Local IS_SH ≥ 1.25 — FAILED on the 251-name proxy. **This is the documented WQ Brain validation gap; final PROMOTE/RESEARCH-ONLY decision deferred to WQ Brain `/alphas/{id}.is` block per CLAUDE.md.**
- [x] Local IS_TO < 0.25 — all 4 well under the ceiling.
- [x] Local OS_SH > 0 — all 4 positive.
- [ ] WQ Brain IS_SH > 1.25 — pending submission (no credentials in this sandbox).
- [ ] WQ Brain IS_TO < 0.25 — pending submission.
- [ ] WQ Brain OS_SH ≥ IS_SH — pending submission.

## Decision

**Decision: PROCEED-TO-SUBMISSION (research-only on local proxy; deferred to WQ Brain).**

The local proxy under-shoots the 1.25 floor for this volume-dispersion-reversal mechanism, but the audits are clean and OS Sharpe is positive on all 4. Per CLAUDE.md the local proxy is intentionally noisy on a 251-name universe and has both false negatives and false positives vs WQ Brain TOP3000 + INDUSTRY-neutralized + truncation=0.08 backtest.

**Next action**: submit `submission_payload.json` to WQ Brain via `scripts/submit_alpha.py` (requires `credential.txt` in repo root). The 4 factors are selected for OS-Sharpe-led composite robustness, not raw IS Sharpe.

## Falsification question

> If this composite headline ranking is wrong by 50%, what is the most likely single cause?

Most likely cause: **field-semantics drift between local `adv20` (dollar volume) and WQ Brain `adv20` (share volume).** The 4 selected expressions deliberately avoid `adv20` and instead use `ts_mean(volume, d)` or `multiply(close, volume)` so the definition is identical on both sides. Test on platform: submit with INDUSTRY neutralization first (most permissive); if that fails, fall back to SECTOR.
