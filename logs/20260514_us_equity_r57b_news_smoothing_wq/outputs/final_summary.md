# R57b news-smoothed alphas

| variant | rationale | SH | TO | FIT | conc | sub | passes? |
|---|---|---:|---:|---:|---|---|---|
| BB4_news_impact_smoothed | rank(ts_mean(impact,20)) * rev * volwt, D=25 | +1.570 | 0.223 | +1.060 | P | P | no |
| BB3_news_novelty_smoothed | rank(ts_mean(novelty,20)) * rev * volwt, D=25 | +1.500 | 0.225 | +0.890 | P | P | no |
| BB5_buyback_x_novelty_smoothed | rank(buyback) * rank(ts_mean(novelty,20)) * rev * volwt, D=25 | +1.210 | 0.220 | +0.610 | P | P | no |

**Survivors: 0/3**
