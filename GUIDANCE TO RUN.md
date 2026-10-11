# Solar Market Reality

Off-grid solar market intelligence. **Dark does not mean no solar**: satellites see grid light, not small
solar home systems. This platform combines nighttime lights with household surveys, population, wealth,
infrastructure and solar resource to estimate where off-grid solar has reached, and where potentially
underserved areas remain. Prototype for Rwanda; designed for other countries and later integration into
Energy Access Explorer (EAE).

> The prototype runs on **synthetic DEMO DATA** by default. Nothing it shows is a real-world finding.

## 1. Problem

Nighttime-light data cannot reliably detect solar home systems or pico-solar. Two equally dark areas can
differ completely in solar uptake, so a light map alone misreads the market.

## 2. Solution

Train a model on survey-derived penetration labels, using nighttime radiance as one feature among several,
then predict a 0-1 **Off-Grid Solar Penetration** surface for every grid cell and derive a
**Potential Market Gap Indicator** (screening only, not proof of viability).

## 3. Architecture

See [docs/architecture.md](docs/architecture.md). In short: pipeline -> ML -> artefacts on disk -> FastAPI -> React/Leaflet.

## 4. Data sources

DHS/MICS/MTF (labels), Black Marble, WorldPop/HRSL, Meta RWI, Gridfinder/OSM/EAE, minigrids, GHI, and GOGLA
(national sanity check only). See [docs/data-sources.md](docs/data-sources.md) and the Data sources page.

## 5-6. ML methodology and spatial validation

Random Forest and XGBoost; random K-fold and **spatial blocked CV with a distance buffer**; MAE, RMSE, R².
The model with the best spatial RMSE is used. See [docs/methodology.md](docs/methodology.md).

## 7. API

Interactive docs at http://localhost:8000/docs. Pass `?country=RW` where relevant.

| Endpoint                                                        | Purpose                                                                                                        |
| --------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| `GET /api/health`                                               | liveness                                                                                                       |
| `GET /api/countries`                                            | configured countries                                                                                           |
| `GET /api/meta`                                                 | run metadata (demo flag, model, features)                                                                      |
| `GET /api/layers`                                               | available map layers                                                                                           |
| `GET /api/map/layer/{layer}`                                    | GeoJSON choropleth (`population`, `night_lights`, `grid`, `solar_resource`, `solar_penetration`, `market_gap`) |
| `GET /api/map/infrastructure`                                   | grid lines and minigrids                                                                                       |
| `GET /api/grid/check?lat=...&lon=...&radius_km=...`             | live OpenStreetMap grid lines, substations and plants around a clicked point                                   |
| `GET /api/cells/{cell_id}`                                      | details for one cell                                                                                           |
| `GET /api/model/performance`                                    | random and spatial CV metrics                                                                                  |
| `GET /api/model/features`                                       | model feature importance                                                                                       |
| `GET /api/statistics?threshold=0.3`                             | summary statistics                                                                                             |
| `GET /api/gogla/comparison`                                     | national sanity check                                                                                          |
| `GET /api/raster/metadata`, `/api/raster/solar_penetration.tif` | raster metadata and download                                                                                   |
| `GET /api/data-sources`, `/api/limitations`                     | documentation content                                                                                          |

## 8. Frontend

React + Vite + React-Leaflet + Axios. Pages: Map (filters, layers, legend, opacity, cell panel, statistics),
Model performance, Data sources, Limitations.

## 9-10. Install and run

Requires Python 3.11+ and Node 18+.

```bash
# backend
cd backend
python -m venv venv && source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
# first start builds the demo dataset and trains the models (about 30 s)
```

```bash
# frontend (second terminal)
cd frontend
npm install
npm run dev          # http://localhost:5173
```

Or with Docker: `docker compose up --build`.

Re-train manually: `cd backend && python -m app.ml.train` (then restart the API or delete nothing: the API reads fresh files on start).

## 11. Demo mode

`DEMO_MODE=true` (default) generates synthetic Rwanda cells, survey clusters, infrastructure and a fake GOGLA
total, then trains and predicts. The UI shows **DEMO DATA** on every page. The generator is
`backend/app/pipeline/demo_generator.py`.

## 12. Replacing demo data with real data

1. Put the files listed in [docs/data-sources.md](docs/data-sources.md) in `backend/data/raw/RW/`.
2. Set `DEMO_MODE=false` in `backend/.env`.
3. Delete `backend/data/processed/RW`, `backend/models/RW`, `backend/outputs/RW`, then run `python -m app.ml.train`.
   A missing file produces an error naming exactly which file to add.
   To add a country: add an entry to `backend/app/countries.py`.

## 13. Limitations

See [docs/limitations.md](docs/limitations.md). Key points: DARK is not NO SOLAR; survey displacement and
year mismatch; low predicted penetration is not commercial viability; validate in the field.

## 14. Future EAE integration

The backend is an independent, read-only service exposing GeoJSON, raster metadata and download, cell-level
predictions, model metadata and layer metadata. EAE can consume `/api/map/layer/{id}` and
`/api/raster/solar_penetration.tif`, or embed the frontend. Next steps: PostGIS storage, vector tiles,
authentication, and per-region accuracy maps.
