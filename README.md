# worldquant_mining — US-stock factor mining

This branch (`claude/us-stock-factor-mining-FyOrT`) bootstraps a
WorldQuant Brain alpha-mining pipeline targeting USA TOP3000 (delay=1)
with the following constraints baked in:

* **In-sample window**: 2019-01-01 .. 2023-12-31 (anchored via
  `startDate`/`endDate` in the simulation request, not a relative
  duration)
* **Out-of-sample window**: 2024-01-01 .. now (sanity check only, never
  used for selection)
* **Hard discovery gate**: IS Sharpe > 1.25 **AND** IS turnover < 0.25
  on every candidate
* **Concurrency**: WQ Brain account here exposes 3 concurrent simulation
  slots; the screener saturates them with a sliding-window submitter
* **No Ollama**: the AI-generation hook in `continuous_evolution.py` is
  re-routed to a Claude-curated alpha library so no local LLM is needed
  (set env var `WQ_USE_OLLAMA=1` to switch back to Ollama)

The base codebase is a fork of
[shu476891497-hash/worldquant-miner](https://github.com/shu476891497-hash/worldquant-miner)
("Generation Two"). Our additions:

| File | Purpose |
|------|---------|
| `generation_two/ollama/claude_static_manager.py` | Drop-in `OllamaManager` replacement returning Claude-curated alpha expressions for the 12 research themes |
| `generation_two/mine_us_factors.py` | Stage-1 screener with three candidate pools (`novel`, `round2`, `round3`) and saturated-slot submission |
| `generation_two/bayesian_tune.py` | Stage-2 Bayesian (skopt GP) hyperparameter tuner over integer placeholders; objective penalises high turnover |
| `generation_two/smoke_test.py` | End-to-end auth + 2-alpha simulation sanity check |
| `generation_two/credential.txt.template` | Template for the gitignored credential file |
| `generation_two/screening_survivors_round2.json` | Empty (round 2 had no qualifiers) — kept for tooling expectations |

We also patched three upstream files (tracked locally, see commit history):

* `generation_two/continuous_evolution.py` — uses Claude shim by default;
  discovery filter requires Sharpe>1.25 AND turnover<0.25; logs turnover.
* `generation_two/core/simulator_tester.py` — `SimulationSettings`
  accepts `startDate` / `endDate`; empty optional fields are stripped;
  fixed-date IS overrides relative `testPeriod`.
* `generation_two/core/credential_manager.py` — auth retries on
  transient SSL / network failures (we observed flaky `cert not yet
  valid` from WQ Brain's edge).

## Setup

```bash
# 1. Get the upstream miner content (we only ship our patches/new code
#    on this branch — the rest is straight upstream).
git clone https://github.com/shu476891497-hash/worldquant-miner.git /tmp/upstream

# 2. Overlay /tmp/upstream/* into ./generation_two (don't overwrite the
#    files this branch already contains: claude_static_manager.py,
#    mine_us_factors.py, bayesian_tune.py, smoke_test.py, the patched
#    continuous_evolution.py / simulator_tester.py / credential_manager.py).

# 3. Install runtime deps.
pip install numpy 'requests>=2.28' scikit-optimize

# 4. Drop credentials into generation_two/credential.txt (two lines —
#    email, password). The file is gitignored.
cp generation_two/credential.txt.template generation_two/credential.txt
edit  generation_two/credential.txt

# 5. Sanity-check auth + a single sim.
python -m generation_two.smoke_test
```

## Stage 1 — pre-screen

```bash
# 30 alphas, sliding window of 3 in-flight simulations, IS=2019-2023
python -m generation_two.mine_us_factors --pool round3 --slots 3
```

Survivors (Sharpe>1.25 AND turnover<0.25) are written to
`generation_two/screening_survivors_round3.json` for stage 2 to consume.

## Stage 2 — Bayesian tune

```bash
python -m generation_two.bayesian_tune \
  --template 'group_neutralize(ts_decay_linear(-ts_rank(returns, $L1), $L2), subindustry)' \
  --space 'L1=60,90,144,252 L2=20,30,40,60' \
  --calls 12 --random-starts 4
```

Picks the IS-Sharpe-max trial that satisfies *both* gates; if none
qualifies, surfaces the runner-up so you can see how close it got.

## Mining results so far

| Round | Pool | Tested | Passed | Best Sharpe / turnover |
|------:|------|------:|------:|------------------------|
| Smoke test | upstream RP | 2 | 1 | +1.480 / 0.500 (failed turnover gate) |
| 1 (`novel`) | 30 fundamental low-turnover | 30 | 0 | +0.600 / 0.045 |
| 2 (`round2`) | 20 smoothed reversal | 20 | 0 | +1.570 / 0.325 |
| 3 (`round3`) | 20 heavy-decay + hump + quality-gated | running | 1 so far | +1.530 / 0.237 (PASS) |

First qualifier: `group_neutralize(ts_decay_linear(-ts_rank(returns, 144), 60), subindustry)` — IS Sharpe 1.530 / turnover 0.237.
