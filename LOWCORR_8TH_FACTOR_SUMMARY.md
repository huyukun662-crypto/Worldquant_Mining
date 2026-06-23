# 8th low-correlation factor — search summary

Goal: a submittable D1 (delay=1, USA) alpha with WQ-platform
`SH > 1.25`, `TO < 0.25`, all IS checks passing, and pairwise PnL
correlation `< 0.5` against the 7 existing reference families A–H.
Per the open-setting directive, every simulation setting **except
region (USA)** is part of the search space.

## Reference families (what we must stay decorrelated from)

| id | recipe (abridged) | universe / neut |
|----|-------------------|-----------------|
| A `58w3aOKM` | pvcorr + vol-normalized short reversal | TOP1000 |
| D `88z6bZEq` | blend(amihud, issuance, turnover, volz) | TOP3000 / SUBIND |
| E `d5x78JRv` | trret + amihud + turnover + volz + gap | TOP1000 |
| H `78wa9R3Q` | **pvcerec** = pvcorr + E-recipe (SH 1.54) | TOP1000 / SUBIND |

Key structural fact: our mining base **`pvcerec`** (pvcorr + trret +
amihud + turnover + volz + gap) is H's exact recipe and also contains
**3/4 of D's flow recipe** (amihud, turnover, volz). So:
- a **value tilt** (cashflow + earnings yield) rotates away from H's
  reversal axis and E, but **cannot** move corr_D (shared flow);
- **TOP2000/3000 inflate corr_D** (D lives in the big universe), so
  **TOP1000 is the right universe** for this base (corr_D ~0.39).

## Two deliverable candidates

### Family I — pasteurization ON (razor-thin, conservative)
`N1pnoddo` — `pvc_val_w060_d14` on TOP1000 / SUBINDUSTRY / trunc 0.08 /
decay 14 / **pasteurization ON**.

```
rank(add( blend(pvcorr,trret,amihud,turnover,volz,gap),
          multiply(0.6, blend(val_cfp, val_ey)) ))
```

- SH **1.26** · TO 0.14 · FIT 1.03 · DD 0.107
- max corr **0.497** (H 0.497) — passes, but margins are ~0.003 corr
  and ~0.01 SH. The feasible window is a single point (w060/d14).

### Robust winner — pasteurization OFF (comfortable margin) ⭐
`2r7JR8KJ` — `pvc_val_w055_d10` on TOP1000 / **INDUSTRY** / trunc 0.08 /
decay 10 / **pasteurization OFF**.

```
rank(add( blend(pvcorr,trret,amihud,turnover,volz,gap),
          multiply(0.55, blend(val_cfp, val_ey)) ))
```

- SH **1.49** · TO 0.201 · FIT 1.23 · DD 0.099
- max corr **0.435** (H 0.435, B 0.379, D 0.277, E 0.221)
- All IS checks pass.

Two levers unlocked this margin, both newly permitted by the
open-setting directive:
1. **INDUSTRY** neutralization (vs H's SUBINDUSTRY) rotates the whole
   vector away from H.
2. **Pasteurization OFF** broke the fitness wall (FIT 0.99→1.23) *and*
   lowered every correlation (max 0.497→0.435).

Caveat: pasteurization OFF disables WQ's delisting/anomaly cleaning, so
the SH is optimistic. The pasteurization-ON arm was exhausted and
confirmed two-sided-squeezed: low decay fails fitness, high decay fails
SH (SH plateau ~1.13–1.15 at the corr<0.47 weights), so a
comfortable-margin winner is **only** reachable with pasteurization OFF
on this base.

## Full pasteur-OFF frontier (all submittable, TOP1000 INDUSTRY)

| id | w / decay | SH | TO | FIT | max corr |
|----|-----------|----|----|-----|----------|
| `Wjp9dngZ` | w045 / d10 | 1.57 | 0.209 | 1.27 | 0.495 |
| `1Y7J61gR` | w050 / d08 | 1.60 | 0.238 | 1.23 | 0.465 |
| `6Xwz3ROK` | w050 / d10 | 1.53 | 0.205 | 1.25 | 0.465 |
| `RRpdqAld` | w050 / d12 | 1.48 | 0.181 | 1.27 | 0.464 |
| **`2r7JR8KJ`** | **w055 / d10** | **1.49** | **0.201** | **1.23** | **0.435** |

Higher value weight → lower corr; lower decay → higher SH but higher
turnover. `2r7JR8KJ` is the best balance.
