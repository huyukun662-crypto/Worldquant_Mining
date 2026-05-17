# R108 cold ops x cold fields

| variant | SH | TO | FIT | checks | conc | sub | max_SC | gate | alpha_id |
|---|---:|---:|---:|---|---|---|---|---|---|
| R108a_tradewhen_hivol_rev | +1.060 | 0.184 | +0.690 | 5/8 | P | P | 0.224 | no | qMnWaJqA |
| R108e_grouprank_subind_mom | +0.950 | 0.311 | +0.520 | 5/8 | P | P | 0.144 | no | O0nr3VXd |
| R108g_buyback_sharesout | +0.440 | 0.045 | +0.290 | 5/8 | P | P | 0.402 | no | vR5kW9XA |
| R108c_quantile_lowvol | +0.190 | 0.091 | +0.060 | 4/8 | P | F(0.05) | 0.352 | no | 2rvOYLeb |
| R108b_persistence_fade | -0.130 | 0.194 | -0.030 | 4/8 | P | F(-0.07) | 0.057 | no | blNRw256 |
| R108h_volrisk_premium | -0.550 | 0.150 | -0.340 | 3/8 | F(0.116274) | F(-0.87) | 0.176 | no | WjNPvL6N |
| R108d_hump_reversal | FAIL | - | - | - | - | - | - | no | - | ERROR: Invalid number of inputs : 2, should be exactly 1 input(s). <linkToCommonErrorMessages>Learn more</linkToCommonEr
| R108f_size_smallcap | FAIL | - | - | - | - | - | - | no | - | WARNING: Incompatible unit for input of "log" at index 0, expected "Unit[]", found "Unit[CSPrice:1,CSShare:1]". <linkToC
| R108i_analyst_earnrev | FAIL | - | - | - | - | - | - | no | - | ERROR: Invalid data field snt1_d1_earningsrevision. <linkToCommonErrorMessages>Learn more</linkToCommonErrorMessages>
| R108j_jumpdecay_hv30 | FAIL | - | - | - | - | - | - | no | - | ERROR: Attempted to use inaccessible or unknown operator "jump_decay". <linkToCommonErrorMessages>Learn more</linkToComm

**Survivors (SH>=1.25 ^ TO<0.20 ^ conc+sub PASS ^ SC<0.7): 0/10**
