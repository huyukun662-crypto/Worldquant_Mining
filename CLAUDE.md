# CLAUDE.md — Worldquant_Mining project notes

This file is read by Claude Code agents when working in this repo. It
captures the architecture, conventions, and known pitfalls so a future
session doesn't have to rediscover them.

## Repo layout

```
.
├── README.md                # short user-facing intro
├── GAP_REPORT.md            # diff: upstream miner vs canonical WQ surface
├── GAP_REPORT.json          # machine-readable diff
├── MINING_REPORT.json       # latest pipeline run output
├── constants/
│   ├── upstream_operatorRAW.json              # snapshot from upstream miner
│   └── upstream_data_fields_USA_TOP3000.json  # snapshot from upstream miner
├── worldquant_mining/       # canonical CATALOG package
│   ├── operators.py         # 176 canonical WQ operators (9 categories)
│   ├── data_fields.py       # PV+GROUP baseline + region helpers
│   ├── factor_templates.py  # 101 Alphas + 26 classical factors
│   └── compare.py           # gap-analysis CLI
├── mining_pipeline/         # SELF-CONTAINED MINING package (no template reuse)
│   ├── data.py              # yfinance OHLCV loader, IS/OS masks
│   ├── operators.py         # numpy implementations of needed ops
│   ├── evaluator.py         # AST-based expression evaluator
│   ├── expressions.py       # random expression generator
│   ├── backtest.py          # vectorized long-short SH + turnover
│   ├── screen.py            # initial filter SH > 1.25 AND TO < 0.25
│   ├── search.py            # Bayes (optuna) + grid HP search
│   └── pipeline.py          # end-to-end orchestrator
├── tests/test_catalogs.py   # 12 sanity tests for canonical catalogs
├── vendor/worldquant-miner/ # vendored upstream (shu476891497-hash)
└── cache/ohlcv.pkl          # cached 251-ticker × 1848-day OHLCV panel
```

## Two distinct concerns — DO NOT MIX

1. **`worldquant_mining/`** is a **catalog**: it documents the operator
   set, data field schema, and 101+classical factor templates. It is the
   reference, used to diff against the upstream miner.

2. **`mining_pipeline/`** is a **mining workflow** that *deliberately
   ignores* the templates in (1). Per the user spec — "完全规避现有的的因子
   template 自行...或者自己创造因子" — the pipeline must NEVER reuse Alpha101
   or the classical factors. It generates fresh expressions from scratch
   using random combinations of operators × PV fields.

   If you find yourself importing from `worldquant_mining.factor_templates`
   inside `mining_pipeline/`, stop — that's a spec violation.

## Backtest authority: WorldQuant Brain `/simulations` is canonical

**All Sharpe / turnover / fitness / IR / drawdown numbers we report MUST
come from WorldQuant Brain's `/simulations` endpoint, not from the
local yfinance backtest.** The local backtest in
`mining_pipeline/backtest.py` is a **fast triage proxy** — useful for
weeding out obvious junk before paying the WQ simulation cost — but its
numbers DO NOT generalize.

### Authoritative thresholds (apply to WQ-platform numbers, not local)

A candidate is reported as a "survivor" iff **all** of these hold on
the values returned by `/alphas/{id}` (the WQ Brain platform's own
backtest):

```
WQ_IS_Sharpe   > 1.25
WQ_IS_Turnover < 0.25
WQ_OS_Sharpe   >= WQ_IS_Sharpe   # (when OS metrics populated)
```

WQ's IS window is fixed at `2019-01-01 → settings.endDate (2023-12-31)`
on this account tier — exactly the user's IS spec. The OS field is
populated asynchronously by WQ; until it is, we report WQ_IS only.
The WQ platform's own `is.checks` block flags `LOW_SHARPE` at the
same 1.25 limit, so a candidate that passes our filter also passes
WQ's stock LOW_SHARPE check.

### Reporting

Files with WQ-platform results (these are the only authoritative
numbers — local backtest numbers in `MINING_REPORT.json` are advisory
proxies only):

- `WQ_SUBMISSION_RESULTS.json` — direct submissions of factors
  surfaced by the local pipeline. Schema: `[{ok, alpha_id, expression,
  alpha:{is:{sharpe,turnover,fitness,returns,drawdown,checks,...}}}]`.
- `WQ_MINING_REPORT.json` — output of `mining_pipeline/wq_pipeline.py`
  with WQ-as-evaluator. Schema: `[{ok, sharpe, turnover, fitness,
  returns, drawdown, checks_passed, checks_total, alpha_id, expression,
  optimized, settings:{universe, delay, decay, truncation,
  neutralization, pasteurization, ...}}]`.

### Evidence

The 2 factors that passed our local gates (`IS_SH > 1.25 ∧ TO < 0.25 ∧
OS_SH ≥ IS_SH`) were submitted to WQ Brain (alpha_ids `0meJlEK1`,
`wpnrmoQ1`). Side-by-side:

|                                                       | local IS | local OS | **WQ Brain SH** | WQ TO | WQ FIT |
|-------------------------------------------------------|---------:|---------:|----------------:|------:|-------:|
| `zscore(ts_decay_linear(ts_mean(ts_std_dev(volume,11),44),23))` | 1.32     | 1.78     | **-0.150**      | 0.026 | -0.07  |
| `scale(ts_mean(ts_decay_linear(divide(adv20,low),15),20))`      | 1.30     | 1.80     | **0.010**       | 0.033 |  0.00  |

Both are noise on WQ Brain. Three structural reasons:

1. Universe — local 251 yfinance large/midcap vs WQ TOP3000 (3,000 names).
2. Backtest mechanics — local equal-weight L/S with L1 = 1; WQ runs
   `INDUSTRY` neutralized with `truncation=0.08` and `pasteurization=ON`.
3. Field semantics — local `adv20 = ts_mean(close*volume, 20)` (dollar
   volume); WQ `adv20 = ts_mean(volume, 20)` (share volume).

### Workflow

The mining loop must end with WQ Brain validation:

```
generate(N candidates)
  -> local backtest pre-screen   (cheap, throws out garbage)
  -> mining_pipeline.wq_pipeline (submits to /simulations, polls,
                                  fetches /alphas/{id})
  -> rank by WQ-returned IS Sharpe (NOT local Sharpe)
  -> filter: WQ_IS_SH > 1.25, WQ_IS_TO < 0.25, WQ_OS_SH >= WQ_IS_SH
  -> survivors -> WQ_MINING_REPORT.json
```

Per the user spec: **expression templates must NOT be reused** (no
Alpha101, no classical-factor library), but the simulation settings
`delay`, `decay`, `truncation`, `universe`, `neutralization`,
`pasteurization` ARE part of the search space and `wq_pipeline.py`
runs Optuna over the joint (expression-windows, settings) space.

Throughput ceiling: ~1 simulation / 86-180s per submission. The user
account allows ~2-3 concurrent submissions. Plan for ~30-60 simulations
per hour; budget candidates accordingly.

### Account tier limits observed on `2445560398@qq.com`

- `delay=0` not available for simulation (HTTP 400 "Delay 0 is not
  available"). `wq_pipeline.SETTING_SPACE['delay'] = [1]` reflects this.
- `ILLIQUID_MINVOL1M` universe returns 0 fields on `/data-fields`.
- USA `/data-fields` ceiling: 6,038 distinct field IDs across all
  documented universes × delays (vs the 7,831 the WQ UI advertises;
  the gap lives behind a higher account tier, not a fetch bug).

### Submit Alpha vs Simulation - two distinct quotas

- **`/simulations`** (backtest): ~2-3 concurrent, ~200-500/day. Used by
  `submit_alpha.py` and `wq_pipeline.py`. Returns IS Sharpe/turnover/etc.
- **Submit Alpha** (add to user's submitted pool): the *act of clicking
  "Submit Alpha" in the web UI*. Cap is **1 concurrent submit operation**
  — while the in-flight submit's IS checks + Self Correlation + Performance
  Comparison are running (~2-5 min total), the next submit is rejected with
  "You have reached the limit of concurrent Submit Alpha".
- **OS checks** on already-submitted alphas (`SHARPE`, `SELF_CORRELATION`,
  `IS_SHARPE`, `OTHERS` under the `os.checks` block) **stay in PENDING until
  the active competition closes** (e.g. `IQC2026S1`). PENDING here is
  normal, not stuck, and **does NOT consume the concurrent Submit slot**.

The script `scripts/submit_alpha.py` calls `/simulations`, not the Submit
Alpha endpoint, so it never touches the Submit Alpha quota.

## Local-proxy pipeline invariants (for the triage stage only)

- **IS window**: 2019-01-01 → 2023-12-31 (set in `mining_pipeline/data.py`)
- **OS window**: 2024-01-01 → today (set in `mining_pipeline/data.py`)
- **Initial screen**: `IS_Sharpe > 1.25` AND `IS_turnover < 0.25`
  (`mining_pipeline/screen.py`)
- **HP search**: Bayes (optuna TPE) by default; grid available; only
  optimizes integer literals in expressions, IS Sharpe is the objective,
  hard constraint `turnover < 0.25` enforced via large negative penalty.
- **Final filter (local)**: `OS_Sharpe >= IS_Sharpe`. With
  `n_candidates=400, seed=19, trials=20` on the 251-ticker panel, ~2
  factors survive.

These thresholds are **placeholders for the local proxy** so the WQ
queue isn't flooded with obvious noise. The authoritative thresholds
are applied AFTER the WQ-Brain submission.

## Running

```bash
# regenerate gap report between upstream and canonical
python -m worldquant_mining.compare

# fast triage on yfinance proxy (do NOT trust the SH numbers)
python -m mining_pipeline.pipeline --n 400 --backend bayes --trials 20 --seed 19

# canonical mining: generate locally, submit to WQ, rank by WQ SH
python -m mining_pipeline.wq_pipeline --n 30

# submit a specific MINING_REPORT.json's factors to WQ Brain
python scripts/submit_alpha.py MINING_REPORT.json

# tests
python -m pytest tests/ -q
```

The local triage takes ~2 minutes on a 251-ticker × 1848-day panel.
Each WQ Brain submission takes 86-180s; budget accordingly.

## Known pitfalls

- **Float-vs-int in evaluator**: `ast.Constant.value` for integer
  literals must be left as `int` (not cast to `float`) — `ts_sum` and
  similar operators slice with `d-1`, which raises `TypeError` on a
  float `d`. Fixed in `mining_pipeline/evaluator.py`.

- **Universe size matters**: a 60-ticker book is too narrow for SH > 1.25.
  Default universe is now 251 tickers (S&P 500 + selected mid-caps), all
  with stable membership across 2019-now. Some tickers (`SQ`, `ANTM`,
  `MMC`, `K`, `HES`) get reported as "delisted" by yfinance and are
  silently dropped — that's fine.

- **`worldquant_mining/factor_templates.py` is for reference only**.
  Do not import it from `mining_pipeline/`.

## Authenticated WQ Brain scrape workflow

Credentials live ONLY in repo-root `credential.txt` (gitignored, chmod
600). Format is JSON list `["username", "password"]` or two newline-
separated lines. Never commit. The current credential is for
`2445560398@qq.com`; rotate via the WQ web UI if exposed.

Scripts:
- `scripts/fetch_data_fields.py REGION UNIVERSE DELAY` — single
  authenticated slice fetch + completeness verifier.
- `scripts/fetch_all_slices.py` — sweep all `(universe, delay)` pairs
  defined in `vendor/worldquant-miner/core/region_config.py` and union.
  Defaults to USA × 5 universes × delay {0, 1} = 10 slices.

The screenshot's per-category totals (analyst=1374 etc.) are unions
across **all** `(delay, universe)` slices. A single slice — e.g. (USA,
TOP3000, delay=1) — caps below those totals because the API exposes
different field subsets per slice (analyst4 reports `count=653` at
delay=1 vs `count=90` at delay=0). Use the union cache
`constants/data_fields_union_USA.json` to compare against the screenshot.

**Critical fetcher pitfall (FIXED in `scripts/fetch_all_slices.py`)**:
the upstream `DataFieldFetcher` has an in-memory cache keyed by `region`
alone. Reusing one fetcher instance silently returns the FIRST slice's
data on every subsequent call, regardless of delay/universe. Always
instantiate a fresh `DataFieldFetcher(...)` per slice.

- **Upstream data field fetcher caps**: the original
  `vendor/worldquant-miner/data_fetcher/data_field_fetcher.py` had stacked
  limits (5 categories, 20 datasets/cat, 10 datasets total, 5 pages,
  50 fields/page → ~2.5K fields/region max). These have been:
  - Categories expanded from 5 → 15 (added pv, sentiment, socialmedia,
    option, earnings, macro, esg, shortinterest, insider, institutional).
  - `limit` per /data-sets call: 20 → 200.
  - `max_datasets` cap: 10 → unlimited.
  - Pagination switched from `page`-based with `max_pages=5` to
    **offset-based** with `MAX_FIELDS_PER_DATASET=50_000` and termination
    when the API's `count` is reached. This was necessary because the
    largest category (Model = 3,296 fields) cannot be captured under any
    `page` cap if the API does not interpret `page` correctly.
  - Page size: 50 (API max — 100 returns HTTP 400
    "pagination limit too high").
  - HTTP 429 backoff: 0.6s throttle between every request, exponential
    backoff (30s → 300s) honoring the API's `Retry-After` header,
    up to 5 retries per call.
  Run `python -m worldquant_mining.verify_completeness <cache.json>` to
  diff a fetched cache against the documented per-category totals in
  `constants/expected_field_counts_USA.json`. The upstream snapshot
  scored 34% (2,663 / 7,831). A union-of-all-slices fetch should
  approach 100%.

- **Cache**: `cache/ohlcv.pkl` (~ 60 MB). Delete to force a re-download
  if the universe changes. yfinance returns a `pd.MultiIndex` columns
  frame; we deliberately persist that shape and re-index on load.

## Branch / git conventions

- Designated dev branch: `claude/complete-search-clone-factors-OrBed`.
- The remote was empty before initial push; there is no `main`. PRs
  cannot be opened against an unrelated-history target without
  force-pushing, which is disallowed by repo policy.
