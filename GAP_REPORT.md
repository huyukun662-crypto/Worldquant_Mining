# WorldQuant Mining — Gap Analysis & Supplement

Goal: Search the cloned `shu476891497-hash/worldquant-miner` repo for its
existing **factor templates**, **data fields**, and **operators**, compare
them directly to WorldQuant Brain's documented surface, and supplement the
gaps.

Run: `python -m worldquant_mining.compare` (regenerates `GAP_REPORT.json`).

---

## 1. Operators

**Upstream**: `constants/upstream_operatorRAW.json` snapshot from the WQ Brain
API — **98 operators** in 9 categories.

**Canonical** (this repo, `worldquant_mining/operators.py`): **176 operators**
covering every documented WQ Brain category.

| Category          | Upstream | Canonical | Added |
|-------------------|---------:|----------:|------:|
| Arithmetic        |       16 |        37 |    21 |
| Logical           |       11 |        13 |     2 |
| Time Series       |       29 |        53 |    24 |
| Cross Sectional   |        8 |        14 |     6 |
| Group             |       10 |        18 |     8 |
| Transformational  |        3 |         8 |     5 |
| Vector            |        4 |        14 |    10 |
| Reduce            |       14 |        14 |     0 |
| Special           |        3 |         5 |     2 |
| **Total**         |   **98** |   **176** |**78** |

The canonical catalog is a strict **superset** of the upstream — no upstream
operator was dropped (verified by `test_canonical_is_superset_of_upstream`).

### Operators added (78)

- **Arithmetic (21)**: `arc_cos, arc_sin, arc_tan, ceiling, cos, exp, floor,
  fraction, log10, log_diff, mod, nan_mask, nan_out, purify, replace, round,
  round_down, s_log_1p, sin, tan, tanh`
- **Logical (2)**: `is_finite, is_not_nan`
- **Time Series (24)**: `inst_tvr, ts_co_kurtosis, ts_co_skewness, ts_count,
  ts_decay_exp_window, ts_entropy, ts_first, ts_ir, ts_kurtosis, ts_max_diff,
  ts_median, ts_min_diff, ts_min_max_cps, ts_min_max_diff, ts_moment,
  ts_partial_corr, ts_percentage, ts_poly_regression, ts_range, ts_returns,
  ts_skewness, ts_theilsen, ts_weighted_decay, ts_weighted_mean`
- **Cross Sectional (6)**: `left_tail, one_side, regression_neut,
  regression_proj, right_tail, truncate`
- **Group (8)**: `group_corr, group_count, group_median, group_normalize,
  group_percentage, group_std_dev, group_sum, group_vector_neut`
- **Transformational (5)**: `clamp, coalesce, convert_dt, filter, pasteurize`
- **Vector (10)**: `vec_choose, vec_count, vec_ir, vec_kurtosis, vec_norm,
  vec_percentage, vec_powersum, vec_range, vec_skewness, vec_stddev`
- **Special (2)**: `is_alpha_universe, size_of`

Each canonical entry carries the same JSON schema as upstream
(`name / category / scope / definition / description / level`) so it merges
cleanly into the miner's existing fetch/cache pipeline.

---

## 2. Data Fields

Upstream caches per `(region, delay, universe)` under
`constants/data_fields_cache_*.json`:

| Region | Universe   | Upstream cache | Status     |
|--------|------------|---------------:|------------|
| USA    | TOP3000    |          2 663 | populated  |
| EUR    | TOP2500    |              0 | **empty**  |
| CHN    | TOP2000U   |              0 | **empty**  |
| ASI    | MINVOL1M   |              0 | **empty**  |
| GLB    | TOP3000    |              0 | **empty**  |
| IND    | TOP500     |              0 | **empty**  |

**5 of 6 region caches are empty.** Field metadata for non-USA regions has to
be re-fetched from the WQ Brain API by the miner; we cannot ship private
field metadata here.

What we **can** supplement is a **universe-agnostic baseline** that is
guaranteed to exist in every WQ Brain equity universe — the inputs every
academic factor (and the 101 Alphas) actually consume:

`worldquant_mining/data_fields.py` adds:

- **`PV_STANDARD_FIELDS` (23)**: `open`, `high`, `low`, `close`, `vwap`,
  `volume`, `returns`, `cap`, `sharesout`, `dividend`, `split_factor`,
  `adv{5,10,15,20,30,40,50,60,81,120,150,180}`.
- **`GROUP_FIELDS` (5)**: `sector`, `industry`, `subindustry`, `country`,
  `exchange` — needed by `group_*` operators.
- **`EXPECTED_CATEGORIES` (14)**: documented WQ Brain top-level categories
  (`pv`, `fundamental`, `analyst`, `news`, `sentiment`, `socialmedia`,
  `option`, `model`, `earnings`, `macro`, `esg`, `shortinterest`, `insider`,
  `institutional`).
- `DEFAULT_UNIVERSES` mapping aligned with upstream `region_config.py`.
- Helpers: `load_region_cache`, `data_fields_by_category`,
  `data_fields_by_subcategory`, `missing_categories`,
  `merge_with_pv_baseline`.

The USA cache covers categories `[pv, fundamental, analyst, news, option,
model, socialmedia, sentiment]` — still missing `earnings, macro, esg,
shortinterest, insider, institutional` (flagged by `compare.py`).

---

## 3. Factor Templates

**Upstream**: NO real factor library. The only hardcoded templates live in
`core/template_generator.py::_generate_fallback_template` and consist of **3
trivial fallbacks**:

```python
"ts_rank(close, 20)"
"-ts_rank(close - ts_mean(close, 20), 10)"
"ts_rank(volume, 20)"
```

Every other expression the miner uses is generated *de novo* by an LLM
(Ollama / DeepSeek). There is no seed library of well-known factors and no
implementation of the canonical 101 Alphas.

**Canonical** (`worldquant_mining/factor_templates.py`) supplements **127
templates**:

- **`ALPHA_101` (101)** — every formula from Kakushadze (2015), *"101
  Formulaic Alphas"* (arXiv:1601.00991, WorldQuant LLC), translated into WQ
  Brain FASTEXPR syntax (e.g. `Ts_ArgMax → ts_arg_max`,
  `IndNeutralize → group_neutralize`, `signedpower → signed_power`).
  Validated by `test_templates_only_use_known_operators_and_fields` — every
  function call resolves to an operator in the canonical catalog.
- **`CLASSICAL_FACTORS` (26)** — momentum (12-1, 6-1, risk-adjusted),
  reversal (1m, 1w, overnight), low-volatility (1m/3m/idiosyncratic/beta),
  liquidity (Amihud, turnover), size, trend, range/volatility (Parkinson,
  Garman-Klass), VWAP deviation, return skew/kurtosis, sector- and
  industry-neutral variants.

Each template entry: `{ id, name, category, expression, source }`.

---

## 4. What this lets the miner do

The upstream miner now has, in this repo:

1. A **complete operator search space** (~80% larger than its previous
   cache) so the LLM/evolutionary search can compose any documented WQ
   Brain operator.
2. A **PV+GROUP baseline** so non-USA regions are not dead weight even
   when their per-region API caches are empty.
3. A **127-expression seed library** of known-good factors that the
   evolutionary engine in `evolution/alpha_evolution_engine.py` can
   crossover/mutate without depending on the LLM to bootstrap.
4. A **diff command** (`python -m worldquant_mining.compare`) to keep the
   gap analysis honest as upstream evolves.

---

## 5. Files added

```
worldquant_mining/
├── __init__.py
├── operators.py            # 176 canonical operators (9 categories)
├── data_fields.py          # PV+GROUP baseline + region helpers
├── factor_templates.py     # 101 Alphas + 26 classical factors
└── compare.py              # python -m worldquant_mining.compare

constants/
├── upstream_operatorRAW.json              # snapshot from upstream
└── upstream_data_fields_USA_TOP3000.json  # snapshot from upstream

tests/test_catalogs.py      # 12 sanity tests (all pass)
GAP_REPORT.md               # this document
GAP_REPORT.json             # machine-readable diff output
```
