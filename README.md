# Worldquant_Mining

Canonical reference catalog of WorldQuant Brain **operators**, **data
fields**, and **factor templates**, built by diffing the cloned
[`shu476891497-hash/worldquant-miner`](https://github.com/shu476891497-hash/worldquant-miner)
against the documented WQ Brain surface and supplementing the gaps.

See [`GAP_REPORT.md`](./GAP_REPORT.md) for the full diff and what was added.

```bash
python -m worldquant_mining.compare    # regenerate gap analysis
python -m pytest tests/                # 12 sanity tests
```

```python
from worldquant_mining import (
    CANONICAL_OPERATORS,        # 176 operators across 9 categories
    PV_STANDARD_FIELDS,         # universe-agnostic price/volume primitives
    ALPHA_101,                  # 101 formulaic alphas (Kakushadze 2015)
    CLASSICAL_FACTORS,          # momentum, reversal, low-vol, liquidity, ...
    ALL_TEMPLATES,
)
```
