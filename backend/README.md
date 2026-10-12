# Backend

## Weekly NASA night-lights ingest

From `backend/`, run `powershell -ExecutionPolicy Bypass -File scripts/schedule/weekly_nightlights.ps1` to fetch and process Rwanda VNP46A2 snapshots. Set `NASA_EARTHDATA_TOKEN` in `backend/.env`. The API reads `data/processed/RW/cells_with_nightlights.csv` as a cache and never calls NASA; an equivalent parquet is written alongside it.

### How to verify night lights are real

Open the latest `data/raw/nightlights_RW_YYYY-MM-DD.meta.json` and copy two or three values from `granules`. Search each exact granule filename in the [NASA LAADS search UI](https://ladsweb.modaps.eosdis.nasa.gov/search/). Confirm the product is VNP46A2, the h/v tile and acquisition day match the metadata, and the listed filename is the same `.h5` that the ingest recorded. The meta file also records source URLs, per-day/tile status, and the `find_latest` listing log. The raw CSV is a cache of sampled values; `no_data` rows remain NaN.

## Feature lineage

| Feature | Source file | Source column | Origin |
| --- | --- | --- | --- |
| `predicted_solar_penetration` | `outputs/RW/cells.csv` | `predicted_solar_penetration` | Selected trained model, applied to processed cell features; its labels come from `training.csv:solar_penetration`. |
| `market_gap_score` | `outputs/RW/cells.csv` | `market_gap_score` | Computed by `app/api/ml/predict.py` from `energy_need_score` and `predicted_solar_penetration`; darkness uses observed radiance. |
| `nighttime_radiance` | `data/processed/RW/cells_with_nightlights.csv` | `nighttime_radiance` | NASA LAADS VNP46A2 `.h5` granules listed in the matching raw snapshot metadata; validated before training. Parquet is an equivalent cache. |
| `solar_resource` map layer | `data/processed/RW/cells_with_survey.csv` | `solar_households` | District-level household survey counts from `Household_Solar_Device_Use_and_Ownership.csv`, attached by `app/pipeline/attach_survey_to_cells.py`. The layer ID is misleading: this is not GHI. The GHI model feature is `solar_resource`, loaded from `data/raw/RW/solar_resource.tif` when supplied; otherwise current real-mode ingestion still uses its documented demo fallback. |

The checked-in `cells_with_survey.csv` is a generated output; inspect its inputs and rerun `python -m app.pipeline.attach_survey_to_cells` to verify survey lineage. Layers backed by demo fallbacks are not verified as real-world observations.

FastAPI service. See the root README for the full guide.

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload          # API docs: http://localhost:8000/docs
python -m app.ml.train --country RW    # rebuild dataset, retrain, rewrite outputs
```

Layout: `app/pipeline` (data), `app/ml` (training, validation, prediction), `app/services` (logic),
`app/api` (routers), `app/schemas` (Pydantic). Artefacts: `data/processed`, `models`, `outputs` (per country code).
