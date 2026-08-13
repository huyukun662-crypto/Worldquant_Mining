# Worldquant_Mining

Canonical reference catalog of WorldQuant Brain **operators**, **data
fields**, and **factor templates**, built by diffing the cloned
[`shu476891497-hash/worldquant-miner`](https://github.com/shu476891497-hash/worldquant-miner)
against the documented WQ Brain surface and supplementing the gaps.

See [`GAP_REPORT.md`](./GAP_REPORT.md) for the full diff and what was added.

```bash
python -m worldquant_mining.compare    # regenerate gap analysis
python -m pytest tests/                # catalog and pipeline sanity tests
```

## A-share factor mining

Generate fresh price/volume expressions for the WorldQuant Brain mainland
China universe without reusing the bundled Alpha101/classical templates:

```bash
# Inspect a deterministic candidate batch without credentials or API calls.
python -m mining_pipeline.wq_pipeline --universe CSI300 --n-exprs 20 \
  --delay 1 --neutralization INDUSTRY --decay 8 \
  --seed 20260726 --dry-run \
  --out CHN_FACTOR_CANDIDATES.json

# Run the authoritative Brain search (requires credential.txt and optuna).
python -m mining_pipeline.wq_pipeline --universe CSI300 --n-exprs 5 --trials 8 \
  --delay 1 --neutralization INDUSTRY --decay 8 \
  --out CHN_WQ_MINING_REPORT.json
```

The workflow fixes `region=CHN`. `--universe` covers all A-shares, the major
SSE/SZSE/CSI broad-market indices, ChiNext, and STAR 50; the user also controls
`--delay`, repeatable `--neutralization`, and `--decay`.
The search jointly tunes expression
lookbacks, decay, truncation, pasteurization, and the neutralization methods
available in that region. Dry-run candidates are explicitly marked
`UNEVALUATED`; only metrics returned by Brain simulations should be treated as
factor performance.

Chinese aliases are accepted for the requested headline indices, for example
`--universe 上证指数` and `--universe 深证成指`.

候选构造、结构预筛选、联合参数搜索及防过拟合逻辑详见
[`docs/CHN_MINING_METHOD.md`](docs/CHN_MINING_METHOD.md)。

```python
from worldquant_mining import (
    CANONICAL_OPERATORS,        # 176 operators across 9 categories
    PV_STANDARD_FIELDS,         # universe-agnostic price/volume primitives
    ALPHA_101,                  # 101 formulaic alphas (Kakushadze 2015)
    CLASSICAL_FACTORS,          # momentum, reversal, low-vol, liquidity, ...
    ALL_TEMPLATES,
)
```
