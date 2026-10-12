# Methodology

Implemented in `backend/app/services/market_gap.py`. Every consumer (map, cell API, reports, assistant,
training pipeline) calls this module.

## Potential Market Gap (market opportunity score)

```
energy_need_score = 0.4 * scale(log(1 + population density))
                  + 0.4 * scale(distance to mapped grid, km)
                  + 0.2 * (1 - scale(log(1 + nighttime radiance)))
solar_uptake      = model prediction (only if trained on real survey labels)
                    else district MTF survey estimate
                    else unknown
market_gap_score  = energy_need_score * (1 - solar_uptake)        # 0-1, displayed as an integer 0-100
```

`scale` clips to the 2nd-98th percentile of Rwandan cells and rescales to 0-1. Weights are configurable
(`NEED_W_*`). Darkness carries the smallest weight because it overlaps with grid distance (Spearman
ρ = −0.27 in the current build). It is treated only as a proxy for grid electricity.

**District survey estimate.** The MTF solar-device file lists only solar-owning households. For each
district: sum of nationally representative household weights over distinct ordinary households with a
device ÷ (WorldPop district population ÷ `AVG_HOUSEHOLD_SIZE` 4.3). Refugee-camp households use a
separate weight and are excluded. Values outside 0-1 are discarded rather than clipped.

**Missing data.** Missing inputs are never imputed. A cell with a missing need input or no uptake
evidence has no score (`evidence_level = insufficient`, `missing_inputs` lists the gaps). Districts with
fewer than 10 sampled solar households are marked `limited`.

**Interpretation.** A deterministic, relative screening heuristic for prioritising field investigation.
It is not calibrated, not a percentage of households, and not evidence of commercial viability. A true
"estimated market gap %" would need household-level grid-connection status and georeferenced ownership,
which the repository does not contain.

## Penetration model (preserved, currently unused)

Random Forest and XGBoost regressors on cell features; random K-fold and spatial blocked CV with a
buffer; the model with the lowest spatial RMSE is selected (`backend/app/api/ml/`). Labels must be
georeferenced survey clusters (`data/raw/RW/surveys.csv`: latitude, longitude, solar_ownership). The
stored models were trained on synthetic demo labels, so the API reports them as not usable and ignores
their predictions.
