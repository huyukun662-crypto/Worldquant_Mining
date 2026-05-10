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

## Pipeline invariants

- **IS window**: 2019-01-01 → 2023-12-31 (set in `mining_pipeline/data.py`)
- **OS window**: 2024-01-01 → today (set in `mining_pipeline/data.py`)
- **Initial screen**: `IS_Sharpe > 1.25` AND `IS_turnover < 0.25`
  (`mining_pipeline/screen.py`)
- **HP search**: Bayes (optuna TPE) by default; grid available; only
  optimizes integer literals in expressions, IS Sharpe is the objective,
  hard constraint `turnover < 0.25` enforced via large negative penalty.
- **Final filter**: `OS_Sharpe >= IS_Sharpe`. This is strict — most
  candidates fail. With `n_candidates=400, seed=19, trials=20` on the
  251-ticker S&P/midcap universe, ~2 factors typically survive.

When tuning, change parameters at the call site, not these invariants.

## Running

```bash
# regenerate gap report between upstream and canonical
python -m worldquant_mining.compare

# run the mining pipeline (uses cache/ohlcv.pkl if present)
python -m mining_pipeline.pipeline --n 400 --backend bayes --trials 20 --seed 19

# tests
python -m pytest tests/ -q
```

The pipeline takes ~2 minutes on a 251-ticker × 1848-day panel.

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
  - Page size: 50 → 100.
  Run `python -m worldquant_mining.verify_completeness <cache.json>` to
  diff a fetched cache against the documented per-category totals in
  `constants/expected_field_counts_USA.json`. The upstream snapshot
  scores 34% (2,663 / 7,831) — the relaxed fetcher should hit ~100%.

- **Cache**: `cache/ohlcv.pkl` (~ 60 MB). Delete to force a re-download
  if the universe changes. yfinance returns a `pd.MultiIndex` columns
  frame; we deliberately persist that shape and re-index on load.

## Branch / git conventions

- Designated dev branch: `claude/complete-search-clone-factors-OrBed`.
- The remote was empty before initial push; there is no `main`. PRs
  cannot be opened against an unrelated-history target without
  force-pushing, which is disallowed by repo policy.
