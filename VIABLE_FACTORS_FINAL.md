# Final viable factors — delivery

23+ rounds of QuantML-port iteration + OpenAlpha port + 18-round
obscure-datafield push = **280+ WQ Brain submissions** on USA TOP3000.

**Gate**: `SH > 1.3` ∧ `turnover < 0.2` ∧ `fitness > 1.0` for Families A–D;
the obscure-datafield push (Families E & F) was run against a stricter
`SH > 1.5` gate.

## 14 viable factors — 6 distinct structural families

### Family A — OHLC channel statistics (3 viable members)
| factor | shape | SH | TO | FIT | ann.ret | alpha_id |
|--------|-------|---:|---:|---:|---:|----------|
| **QM_R6_01** | body variance asymmetry | **1.51** | 0.06 | **2.38** | 31% | `58Ln2d05` |
| **OA24** | OHLC extreme variance asymmetry | **1.47** | 0.07 | **2.47** | 35% | `vR5wxKO3` |
| **QM_R16_05** | body signed-squared mean | **1.35** | 0.10 | 1.32 | 12% | `3qEwlObQ` |

### Family B — Session-mean decomposition
| factor | shape | SH | TO | FIT | ann.ret | alpha_id |
|--------|-------|---:|---:|---:|---:|----------|
| **QM_R8_03** | overnight mean − intraday mean | **1.50** | 0.10 | 1.80 | 18% | `O0nOQGJb` |

(QM_R11_05 is a near-duplicate of R8_03 with peer-residualisation; not counted as independent.)

### Family C — Volume-weighted return mean (NEW this push)
| factor | shape | SH | TO | FIT | ann.ret | alpha_id |
|--------|-------|---:|---:|---:|---:|----------|
| **QM_R22_02F** | −Mean(R·V, 60)/Mean(V, 60) | **1.44** | 0.08 | **2.12** | 27% | `0mAlMxk6` |

### Family D — Cross-stock peer distance (NEW this push)
| factor | shape | SH | TO | FIT | ann.ret | alpha_id |
|--------|-------|---:|---:|---:|---:|----------|
| **QM_R23_02F_MKT_t10** | Mean((C − peer_mean)/C, 60) @ MARKET-neut t=0.10 | **1.34** | **0.01** | **1.67** | 20% | `kqn7oJ56` |
| **QM_R23_02F_MKT_t15** | same expression @ t=0.15 (variant) | **1.37** | **0.01** | **1.83** | 22% | `omnpojdm` |

### Family E — Multiplicative CoV-blend of obscure liquidity-risk fields (NEW — obscure-datafield push)

Built entirely from obscure `mdl77` liquidity-risk model fields (userCount ≤ 34,
several uc=1 — effectively undiscovered). **Zero overlap with the OHLC-PV
Families A–D** — uses no price, open, high, low, close, volume or returns.
Shape = product of two *coefficient-of-variation* signals
`CoV(x,W) = ts_std_dev(x,W) / ts_mean(x,W)`.

| factor | shape | SH | TO | FIT | alpha_id |
|--------|-------|---:|---:|---:|----------|
| **QM_D12_05** | −CoV(milliq,150)·CoV(bap20d,150) | **1.89** | 0.04 | **2.79** | `JjnYx5bO` |
| **QM_D12_04** | −CoV(milliq,100)·CoV(bap20d,100) @ decay=0 | **1.83** | 0.05 | **2.73** | `JjnY791A` |
| **QM_D10_05** | −CoV(milliq,100)·CoV(bap20d,100) @ decay=4 | **1.80** | 0.05 | **2.67** | `88O7Q76V` |
| **QM_D15_05** | −CoV(milliq)·CoV(bap20d)·CoV(cvvolp20d) (triple) | **1.74** | 0.05 | **2.61** | `WjNNXwGO` |
| **QM_D12_02** | −CoV(milliq,100)·CoV(cvvolp20d,100) | **1.59** | 0.05 | **1.81** | `omnAqegv` |

`milliq` (Amihud illiquidity) is the essential component — pairing it with a
second liquidity-instability CoV (`bap20d` bid-ask proxy, or `cvvolp20d`
volume-vol/price-vol ratio) clears the gate with large margin. Single-field
CoVs cap at SH≈1.49; the *multiplicative interaction* is what breaks through.

Late addition (D15): a 3-way product `CoV(milliq)·CoV(bap20d)·CoV(cvvolp20d)`
also clears, at SH=1.74 — the multiplicative-blend structure works at arity
2 and 3, with diminishing returns at arity 3.

### Family F — Conditional-firing trade_when (NEW — obscure-datafield push)

A structurally different shape than Family E: instead of multiplying two
CoVs, wrap a SINGLE `-CoV(milliq, 100)` signal in a `trade_when(...)`
conditional that only fires on certain days. The signal then takes a flat
−1 stance off-gate.

| factor | shape | SH | TO | FIT | alpha_id |
|--------|-------|---:|---:|---:|----------|
| **QM_D18_05** | trade_when(vol > ts_mean(vol,120), −CoV, −1) @ decay=0 | **1.55** | 0.04 | **1.67** | `KPnnEd7p` |
| **QM_D18_02** | trade_when(vol > ts_mean(vol,60)·1.5, −CoV, −1) | **1.53** | 0.04 | **1.64** | `0mAA7dLv` |

D17–D18 tuning grid found: stricter volume gates beat looser ones; volume
window 60 < 120; `returns > 0` gate (SH=1.42) underperformed volume gates;
self-referential `CoV > rolling-avg(CoV)` gate just missed at SH=1.49.

---

## Final expressions + complete settings

### #1 QM_R6_01
```
ts_std_dev((close - open) / open * less(close - open, 0), 100)
- ts_std_dev((close - open) / open * greater(close - open, 0), 100)
```
`universe=TOP3000  delay=1  decay=4  neut=INDUSTRY  trunc=0.08`

### #2 OA24
```
ts_std_dev(low  / ts_delay(close, 1) - 1, 100)
- ts_std_dev(high / ts_delay(close, 1) - 1, 100)
```
`universe=TOP3000  delay=1  decay=0  neut=INDUSTRY  trunc=0.08`

### #3 QM_R16_05
```
-1 * ts_mean(signed_power(ts_zscore((close - open) / open, 60), 2), 60)
```
`universe=TOP3000  delay=1  decay=4  neut=INDUSTRY  trunc=0.05`

### #4 QM_R8_03
```
ts_mean(open / ts_delay(close, 1) - 1, 60)
- ts_mean(close / open - 1, 60)
```
`universe=TOP3000  delay=1  decay=4  neut=SUBINDUSTRY  trunc=0.05`

### #5 QM_R22_02F
```
-1 * ts_mean(returns * volume, 60) / ts_mean(volume, 60)
```
`universe=TOP3000  delay=1  decay=4  neut=INDUSTRY  trunc=0.05`

### #6 QM_R23_02F_MKT_t10
```
ts_mean((close - group_mean(close, 1, subindustry)) / close, 60)
```
`universe=TOP3000  delay=1  decay=4  neut=MARKET  trunc=0.10`

### #7 QM_R23_02F_MKT_t15 (variant of #6)
Same expression as #6, only `trunc=0.15` instead.

### #8 QM_D12_05 — Family E champion (obscure-datafield push)
```
-1 * ts_std_dev(mdl77_liquidityriskfactor_milliq, 150)
   / ts_mean(mdl77_liquidityriskfactor_milliq, 150)
   * ts_std_dev(mdl77_liquidityriskfactor_bap20d, 150)
   / ts_mean(mdl77_liquidityriskfactor_bap20d, 150)
```
`universe=TOP3000  delay=1  decay=4  neut=SUBINDUSTRY  trunc=0.05`

### #9 QM_D12_04 (variant of #8)
Same expression as #8 with windows W100 and `decay=0`. SH=1.83.

### #10 QM_D10_05 (variant of #8)
Same expression as #8 with windows W100 and `decay=4`. SH=1.80.

### #11 QM_D12_02 (Family E, second field-pair)
Same shape as #8 but the second field is `cvvolp20d` instead of `bap20d`,
windows W100, `decay=4`. SH=1.59.

### #12 QM_D15_05 (Family E triple product)
```
-1 * ts_std_dev(mdl77_liquidityriskfactor_milliq,    100)
   / ts_mean   (mdl77_liquidityriskfactor_milliq,    100)
   * ts_std_dev(mdl77_liquidityriskfactor_bap20d,    100)
   / ts_mean   (mdl77_liquidityriskfactor_bap20d,    100)
   * ts_std_dev(mdl77_liquidityriskfactor_cvvolp20d, 100)
   / ts_mean   (mdl77_liquidityriskfactor_cvvolp20d, 100)
```
`universe=TOP3000  delay=1  decay=4  neut=SUBINDUSTRY  trunc=0.05`. SH=1.74.

### #13 QM_D18_05 — Family F champion (trade_when conditional)
```
trade_when(
  volume > ts_mean(volume, 120),
  -1 * ts_std_dev(mdl77_liquidityriskfactor_milliq, 100)
     / ts_mean   (mdl77_liquidityriskfactor_milliq, 100),
  -1
)
```
`universe=TOP3000  delay=1  decay=0  neut=SUBINDUSTRY  trunc=0.05`. SH=1.55.

### #14 QM_D18_02 (Family F variant)
Same shape as #13 but gate is `volume > ts_mean(volume, 60) * 1.5` and
`decay=4`. SH=1.53.

Common across all 14: `instrumentType=EQUITY, region=USA, pasteurization=ON, unitHandling=VERIFY, nanHandling=OFF, language=FASTEXPR, visualization=false, maxTrade=OFF, testPeriod=P0Y0M`.

---

## Correlation map (qualitative; WQ async PENDING)

|        | A (OHLC) | B (session) | C (vol-weighted ret) | D (peer-dist) | E (obscure-CoV-blend) | F (trade_when) |
|--------|----------|-------------|----------------------|---------------|-----------------------|----------------|
| **A**  | within-family **high** | low | medium | low | **expected very low** | **expected low-medium** |
| **B**  | low | — | medium | low | **expected very low** | **expected very low** |
| **C**  | medium | medium | — | low | **expected very low** | **expected low** |
| **D**  | low | low | low | identical (#6=#7) | **expected very low** | **expected very low** |
| **E**  | very low | very low | very low | very low | within-family **high** | **expected high** (shared base CoV) |
| **F**  | low-med | very low | low | very low | high | within-family **high** (same wrapper shape) |

Families A–D use only PV inputs; Families E–F use only `mdl77` model fields and `volume`. **Expected E↔A–D correlation is very low** — different inputs and different shape entirely. Family F shares the `CoV(milliq)` base with Family E so within-pair correlation is high, but the conditional gate decorrelates it somewhat from Family E.

---

## Empirical findings (150+ submissions)

1. **Hard SH ceiling ≈ 0.94 on close-to-close return-only factors** under USA TOP3000 INDUSTRY-neut + 0.08 trunc. Confirmed multiple times.
2. **OHLC channel** (body, extremes) is required for SH > 1.25 on the variance-asymmetry shape.
3. **Session decomposition** is the only non-variance shape that broke the gate easily.
4. **Volume-weighted return mean** (Family C) — flipping sign was critical: the raw signal had SH=-1.44 (continuation), the flip gives SH=+1.44 (reversal).
5. **Cross-stock peer-distance** (Family D) lifted from SH=1.06 (INDUSTRY-neut) → 1.24 (MARKET-neut) → 1.34 (MARKET + trunc=0.10) → 1.37 (MARKET + trunc=0.15). Both **MARKET-neut** AND **looser truncation** were needed; either alone fell short.
6. **Looser truncation is signal-specific**: peer-distance gained from t=0.10/0.15, adv-rel-volume LOST from looser truncation. No universal recipe.
7. **`signed_power(x, 2)` outperforms `power(x, 3)`** on the body-skew shape (R10_04 SH=1.07 → R16_05 SH=1.35).
8. **Smaller universes (TOP500/TOP1000) hurt every factor tested** — TOP3000 is the right granularity.
9. **Rank/z-sum composites consistently underperformed their best component** (R3_05, R4_04, R5_02, COMP1). Cross-sectional correlations too high among related shapes.
10. **Shapes that failed to reach SH=1.3** (across 50+ attempts): auto-correlation, coefficient of variation, sign-streak, rank-reversal, volume-shock, Sortino, Sharpe ratio, regime-vol ratio, peer-relative momentum, vol-managed return, omega gain/loss, crash frequency, vwap-deviation vol, body autocorr, range-body coupling, vol-direction asym, GK-style range vol diff, Kaufman efficiency, WVAD, close-vwap path corr, volume-weighted close-vs-mid, beta time-variation, intraday body kurtosis, conditional reversal, Z-score velocity, peer-relative idio-vol.

### Obscure-datafield push (rounds D1–D18, 90 submissions)

Goal: build factors from the rarest `mdl77` model data-fields (low userCount)
to minimise correlation with the OHLC-PV Families A–D.

11. **Pure obscure single-field factors cap at SH≈1.49** on USA TOP3000. The
    best single field is `mdl77_liquidityriskfactor_milliq` (Amihud illiquidity);
    its coefficient-of-variation `CoV = Std/Mean` reaches SH=1.49 at W100,
    SUBINDUSTRY-neut — but window/decay/trunc/universe/pasteurization/rank/zscore
    levers are all exhausted there.
12. **The breakthrough is a multiplicative interaction.** Multiplying two
    independent liquidity-instability CoVs (`milliq` × `bap20d`) clears the gate
    at SH=1.80–1.89 — far above either component alone. Additive composites
    (rank-sum, z-sum) still dilute (D3 confirmed); only the *product* works.
13. **`milliq` is the essential factor of the product.** `bap20d`×`volto`
    (no `milliq`) only reaches SH=0.92; any pair *containing* `milliq` clears
    or approaches the gate.
14. **Variance, not level, is the carrier.** `ts_mean(milliq)` (level) gives
    SH≈0.62; `ts_std_dev(milliq)` (volatility) gives SH≈1.00; `Std/Mean` (CoV)
    gives SH≈1.49 — and the CoV product gives SH≈1.89.
15. **SUBINDUSTRY-neut beats INDUSTRY and MARKET** for the liquidity-risk
    family (opposite of the peer-distance Family D, which wanted MARKET).

---

## What's in this PR

- `scripts/openalpha_factors.py`, `submit_openalpha*.py` — OpenAlpha port (34 candidates → OA24).
- `scripts/wq_runner.py` — reusable runner.
- `scripts/submit_quantml_r{1..23}.py` + `submit_quantml_rN.py` — 23+1 QuantML rounds.
- `scripts/submit_quantml_{O1,F1,F2}.py` — setting-grid and fundamental rounds.
- `scripts/submit_quantml_D{1..18}.py` — obscure-datafield push (Families E & F).
- `WQ_OPENALPHA_RESULTS.json`, `WQ_QUANTML_RESULTS.json` — full submission records (280+ entries).
- `VIABLE_FACTORS_FINAL.md` — this doc.

## Reproducing

```bash
echo '["<wq-username>","<wq-password>"]' > credential.txt && chmod 600 credential.txt

python scripts/submit_openalpha.py            # delivers OA24
python scripts/submit_openalpha_fixes.py
python scripts/submit_openalpha_round3.py

for i in $(seq 1 23); do
  python scripts/submit_quantml_r${i}.py
done
python scripts/submit_quantml_rN.py
```
