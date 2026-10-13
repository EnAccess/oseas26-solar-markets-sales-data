<p align="center">
  <a href="https://github.com/EnAccess/oseas26-solar-markets-sales-data">
    <img
      src="https://drive.google.com/uc?id=1gtL_p7l3HbOcCzc09A7KW5d7B5qn-BDs"
      alt="Identifying solar markets based on sales data"
      width="640"
    >
  </a>
</p>
<p align="center">
    October 26-27 | Open Source in Energy Access Symposium Hackathon | Kigali, Rwanda
</p>

---

# Identifying Solar Markets Based on Sales Data

Build a market-reality layer for the
[Energy Access Explorer (EAE)](https://www.energyaccessexplorer.org) that
distinguishes where the off-grid solar market has failed to arrive from where it
has quietly succeeded.

## Abstract and goal

Grant capital and results-based financing for off-grid solar tend to flow toward
territories that are already commercially viable, because those are the
territories that are visible in the data. Places that remain dark across every
available dataset also remain dark in most funding decisions.

The sector does not lack maps of where energy demand should exist; the Energy
Access Explorer (EAE) already provides these, running multi-criteria analysis on
the fly across normalized demand and supply layers so that planners can reweight
criteria interactively and rank priority areas from their own perspective. What
EAE currently doesn't include is a **market-reality layer**: a view of where the
off-grid solar market has failed to arrive, and a means of distinguishing that
from where it has quietly succeeded. This challenge asks teams to build that layer
for a country of their choice, integrating sales data.

VIIRS and Black Marble have a radiance detection floor well above the emissions of
a solar home system or pico-lantern, which means a village where every household
owns a solar home system registers as dark, and a village with no energy access at
all also registers as dark. The intuitive formulation of this challenge — in which
dense population combined with zero nighttime lights is taken to indicate an
underserved community — will therefore surface precisely those territories where
the off-grid sector has already done its best work. Darkness indicates the absence
of a grid connection, which defines the addressable market for distributed
renewable energy, but it says nothing about whether that market has been served.

Actual penetration must be measured from sources that measure penetration, which
is why georeferenced household survey data (DHS and MICS geo-clusters carrying
solar panel ownership and electricity source, and ESMAP Multi-Tier Framework
surveys carrying explicit Tier 0 to 5 access) forms the backbone of this
challenge. GOGLA sales data is semi-annual, affiliate-reported, and aggregated to
country and product category, with company-level detail held confidential under a
three-data-point rule and no public access to the underlying platform, so it
should be treated as a national control total against which a survey-derived
penetration surface is calibrated — rather than as a pixel-level penetration layer
in its own right.

## Expected outcomes

Three core deliverables (plus an optional prototype):

- **Predictive model of off-grid solar penetration:** an open-source model trained
  on georeferenced survey labels, with blocked cross-validation performance
  reported alongside random cross-validation performance, and feature analysis
  framed as hypotheses rather than findings.
- **EAE-conformant layer:** at least one raster, with values normalized 0 to 1 and
  direction documented, accompanied by metadata covering source, year, method, and
  known limitations.
- **Documentation and limitations statement:** a brief write-up describing the
  datasets used, the modelling approach, the validation methodology, and accuracy
  metrics, together with a one-page statement of what the model cannot see, where
  it will be wrong, and who it would misallocate capital toward.
- **Interactive prototype (optional):** a map in which priority zones are visible,
  inspectable, and traceable back to the layers that produced them.

## Implementation: Solar Market Reality

Solar Market Reality is this repository's implementation of the market-reality layer for Rwanda. It is a
FastAPI backend plus a React + Leaflet frontend, with real, locally cached data and no synthetic values in the
default build. The sections below describe what is actually implemented and tested.

### What it does

- **Explorer map** of 5 km analysis cells (1,203 cells covering Rwanda). Layers: Potential Market Gap
  (default), Population Density, Nighttime Lights, Distance to Mapped Grid, Solar Ownership (district
  survey) and Relative Wealth. Each layer has a legend with units, source, date and a count of cells with
  no data.
- **Mapped electricity infrastructure overlay**: OpenStreetMap power lines, minor lines and cables,
  substations and power plants, styled by class. There is no verified minigrid dataset, so no minigrids
  are drawn.
- **Location details**: every indicator for a cell, with its unit, source, date and evidence type
  (observed, external estimate, derived, model prediction), plus the opportunity score, what drives it,
  and an interpretation.
- **Manual selection and reports**: select cells with "Add to selection", Ctrl/Cmd + click, the "click
  adds to selection" mode, or by searching a district/province and adding all its cells. Review the
  selection, then generate a report preview or download a **PDF** (tables, charts, interpretation, sources,
  limitations) or **CSV**, covering only the selected cells.
- **AI assistant** ("Ask the data" tab): answers questions about locations, indicators, comparisons and
  reports. It calls read-only backend tools over the same services. It is optional and needs
  `ANTHROPIC_API_KEY`.
- **About, Data sources, Model and Limitations pages**, generated from the live dataset metadata.

### Data in the current build

| Indicator | Source (file) | Date / version | Unit | Status |
| --- | --- | --- | --- | --- |
| Population, density | WorldPop 2020 1 km unconstrained, `data/raw/RW/population.tif` | 2020 | people, people/km² | real (CC BY 4.0) |
| Nighttime radiance | NASA VNP46A2 via LAADS, `data/processed/RW/cells_with_nightlights.csv` | single-day sample, ingest Oct 2026 | nW/cm²/sr | real; raw snapshot metadata not in this checkout |
| Distance to grid, grid presence, overlay | OpenStreetMap via Overpass, `data/raw/RW/grid.geojson`, `power_facilities.geojson` | OSM snapshot 2026-10-12 | km, yes/no | real (ODbL) |
| Solar ownership | MTF household survey, solar device module, `data/processed/RW/Household_Solar_Device_Use_and_Ownership.csv` | year not recorded in file | % of households (district estimate) | real, district level |
| Relative wealth | Meta RWI via HDX, `data/raw/RW/relative_wealth.csv` | 2021 | RWI | real (CC BY-NC 4.0) |
| Districts / provinces | GADM level 2, `data/processed/RW/rwanda_districts.geojson` | – | – | real |
| Solar resource (GHI), minigrids, GOGLA, GPS survey clusters | – | – | – | **not available**: left missing, never substituted |

`data/raw/` is gitignored. The processed CSV (`data/processed/RW/cells_features.csv`) and its
provenance (`data/processed/RW/meta.json`: source, licence, retrieval and build dates, file paths) are
committed, so the app runs from a fresh clone without downloading anything.

### Potential Market Gap: method

The calculation lives in one place, `backend/app/services/market_gap.py`, and is used by the map, cell API,
reports, assistant and training pipeline.

```
energy_need_score = weighted mean (0.4 / 0.4 / 0.2) of
    scaled log(1 + population density)       more people      -> higher
    scaled distance to mapped grid           farther          -> higher
    1 - scaled log(1 + nighttime radiance)   darker           -> higher   (grid proxy only)
    scaling: 2nd-98th percentile of Rwandan cells, missing values stay missing
solar_uptake      = predicted penetration from a model trained on REAL survey labels, if available;
                    otherwise the district MTF survey estimate
                    (survey-weighted solar-owning households / (WorldPop district population / 4.3));
                    otherwise unknown
market_gap_score  = energy_need_score x (1 - solar_uptake)      displayed as an integer 0-100
```

- **What it is:** a deterministic heuristic that gives a relative priority score for field investigation.
  It is **not** a calibrated model, **not** a percentage of households lacking solar, and **not** evidence
  of commercial viability. The data cannot support a true "market gap %": the survey has no GPS and lists
  only solar owners, and grid-connection status per household is unknown.
- **Missing data:** with no uptake evidence (e.g. a cell whose centre is outside every district) or a
  missing need input, the cell gets **no score** and `evidence_level = insufficient`. It is never scored
  as if solar ownership were zero.
- **Evidence levels:** `indicative` (district survey with ≥ 10 sampled solar households, or a real-label
  model), `limited` (fewer than 10 sampled households), `insufficient` (no score).
- **Darkness ≠ no solar:** radiance only enters the need score as a grid proxy, with the smallest weight
  because it overlaps with grid distance (Spearman ρ = −0.27 in the current build).
- **Default priority cut-off:** 0.55, roughly the top fifth of scored cells in the current build;
  adjustable on the map.
- **Predicted solar penetration:** the stored Random Forest / XGBoost models (`backend/models/RW`) were
  trained on synthetic demo labels. The API detects this (`metrics.is_demo` ≠ dataset) and does **not**
  use or display their predictions. The training pipeline is preserved: add georeferenced survey
  clusters as `data/raw/RW/surveys.csv` and run `python -m app.api.ml.train` to enable them.

### How the assistant retrieves evidence

`POST /api/assistant/ask` runs a bounded tool-use loop (at most 6 rounds) with Claude
(`ASSISTANT_MODEL`, default `claude-opus-5-5`) over six read-only tools: `resolve_location`,
`get_cell_evidence`, `summarize_cells`, `compare_areas`, `get_methodology` and `prepare_report`. Each tool
calls the same services as the API, so assistant answers use the map's numbers. A deterministic scope
guard declines unrelated questions before any model call. Tool inputs are validated and size-limited,
and no code, SQL, shell or file access is reachable. Each response returns the evidence it used, which
the UI shows under "Data used". Without `ANTHROPIC_API_KEY` the endpoint returns only the retrieved
evidence and a setup message, never a simulated answer. Only aggregated project data is sent to the
provider. Server-side refusal fallbacks (`fallbacks: "default"`) are enabled.

### Install and run

Requires Python 3.11+ and Node 18+.

```bash
# backend
cd backend
python -m venv .venv && .venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt                       # runtime deps + pytest
cp .env.example .env                                      # DEMO_MODE=false is the default
uvicorn app.main:app --reload                             # http://localhost:8000/docs

# frontend (second terminal)
cd frontend
npm install
npm run dev                                               # http://localhost:5173
```

Environment variables (`backend/.env`): `DEMO_MODE` (false = real data), `UNDERSERVED_THRESHOLD` (0.55),
`NEED_W_*` (need weights), `AVG_HOUSEHOLD_SIZE` (4.3, used for the district solar share),
`NASA_EARTHDATA_TOKEN` (night-light ingest only), `ANTHROPIC_API_KEY`, `ASSISTANT_MODEL`,
`ASSISTANT_TIMEOUT_S`. Keys stay on the backend. Frontend: `VITE_API_URL` / `VITE_PROXY_TARGET`.

### Refresh and rebuild data

From `backend/`:

| Step | Command | Writes |
| --- | --- | --- |
| Population and wealth | `python scripts/ingest/fetch_population_wealth.py` | `data/raw/RW/population.tif`, `relative_wealth.csv` + `.meta.json` |
| Electricity infrastructure | `python scripts/update_grid_from_overpass.py` (rebuilds automatically; `--no-build` to skip) | `data/raw/RW/grid.geojson`, `power_facilities.geojson`, `infrastructure.meta.json` |
| Night lights (needs `NASA_EARTHDATA_TOKEN`) | `powershell -ExecutionPolicy Bypass -File scripts/schedule/weekly_nightlights.ps1` | dated raw snapshots + `data/processed/RW/cells_with_nightlights.csv` |
| Processed dataset | `python -m app.pipeline.build` | `data/processed/RW/cells_features.csv`, `infrastructure.geojson`, `meta.json` |

The API loads the processed CSV once, caches the map layers in memory (warmed at startup) and reloads
automatically when a processed file changes on disk. It never calls NASA, WorldPop, HDX or Overpass while
serving requests. To verify the night-light values, open the latest
`data/raw/nightlights_RW_YYYY-MM-DD.meta.json` and search the listed granule names in the
[NASA LAADS search UI](https://ladsweb.modaps.eosdis.nasa.gov/search/).

### API

Interactive docs: `http://localhost:8000/docs`. Main endpoints: `GET /api/meta`, `GET /api/layers`,
`GET /api/map/layer/{market_gap|population|night_lights|grid|survey_solar|relative_wealth|population_total|solar_penetration}`,
`GET /api/map/infrastructure`, `GET /api/cells/{cell_id}`, `GET /api/statistics`,
`GET /api/locations/search?q=`, `POST /api/reports/{summary|csv|pdf}` (`{"cell_ids": [...], "threshold": 0.55}`,
max 500 cells), `GET /api/assistant/status`, `POST /api/assistant/ask`, `GET /api/data-sources`,
`GET /api/limitations`, `GET /api/model/performance`. The map layer previously called `solar_resource`
(which actually showed survey counts) is now `survey_solar`.

### Tests

```bash
cd backend && python -m pytest -q        # market-gap unit tests, pipeline/schema, API consistency, reports, assistant (mocked)
cd frontend && npm test && npm run build # Vitest + Testing Library component tests, production build
```

### Known limitations

- Solar uptake evidence is district-wide, from 2-47 sampled solar households per district, and survey
  year is unknown. Cells in one district share one uptake value.
- The district share mixes MTF survey weights with WorldPop 2020 population and an assumed household
  size of 4.3.
- No georeferenced survey labels are available, so there is no validated cell-level penetration model.
- Night lights are a single-day VNP46A2 sample (clouds, moonlight and fires can affect it), and its
  acquisition date can't be verified from this checkout.
- OpenStreetMap infrastructure is incomplete, and mapped lines do not mean connected households.
- 204 cells near the border have centres outside the district polygons. They have no survey evidence
  and no score. Border and lake cells have under-counted or missing population.
- GOGLA sales, solar resource (GHI) and minigrid datasets are not in the repository.

## Required knowledge

### Stack

- **Python geospatial:** GeoPandas for vector processing; Rasterio / GDAL for
  raster analysis.
- **Machine learning:** Scikit-learn, XGBoost, LightGBM for modelling off-grid
  solar penetration.
- **Geospatial and socio-economic data:** NASA Black Marble; WorldPop or Meta High
  Resolution Settlement Layer for population; Meta Relative Wealth Index via the
  Humanitarian Data Exchange; Gridfinder or OpenStreetMap for grid infrastructure.

#### Solar market and sales data

This is the suggested group that allows a team to distinguish a village the market
has already served from a village it has never reached. Teams are encouraged to
identify more data during the hackathon. Each source is listed with the resolution
it operates at, because that determines the job it can do:

1. **GOGLA Sales and Impact Data:** unit sales by country, region, and product
   category, split between cash and PAYGo, reported semi-annually and annually by
   GOGLA affiliates. Published as public reports with accompanying tables. The
   underlying platform at data.gogla.org is restricted to companies that report
   into it, and a three-data-point rule enforces confidentiality, so
   distributor-level footprints are not obtainable. *Resolution:* national.
   *Job:* control total.
2. **Off-Grid Solar Market Trends Report (GOGLA and ESMAP):** market sizing,
   investment gap, and outlook. *Resolution:* regional and national. *Job:*
   context and sanity check.
3. **GOGLA deals database:** investment flows into off-grid solar companies from
   2012 onward. *Resolution:* company. *Job:* identifying which distributors are
   capitalized to expand into a new territory.
4. **PAYGo PERFORM:** standardized key performance indicators for PAYGo company
   performance, including portfolio quality and repayment. *Resolution:* company,
   aggregated. *Job:* identifying which distributors could absorb and deploy a
   grant.
5. **AMDA Benchmarking Africa's Minigrids:** operational and financial benchmarks
   aggregated across member developers and countries. *Resolution:* operator,
   aggregated. *Job:* context on mini-grid viability.
6. **ENERGYDATA.INFO (ESMAP / World Bank):** open data registry with API access,
   carrying existing and candidate mini-grid project datasets, grid network data,
   and the Africa Electricity Grids Explorer. *Resolution:* point and line
   geometry. *Job:* the only georeferenced market and infrastructure source in
   this group.
7. **Infrastructure data available in Energy Access Explorer.**
8. **National results-based financing and electrification programme records:**
   connection counts and subsidy disbursements published by rural electrification
   agencies and programme administrators. *Resolution:* sub-national where
   available, variable quality. *Job:* validation and ground-truthing.
9. **DHS and MICS geo-clusters, and ESMAP Multi-Tier Framework surveys:**
   household solar panel ownership, electricity source, and Tier 0 to 5 access,
   carried at cluster level with displaced GPS. *Resolution:* point. *Job:* this
   is the only source in the challenge that measures penetration at a location,
   and it is therefore the label.

### Programming languages

- Python
- SQL
- JavaScript / any other for frontend

### Helpful experiences

- Experience with Geospatial Analysis and Remote Sensing using, for example,
  Python, Google Earth Engine, PostGIS, QGIS, GeoJSON, GeoParquet, or spatial SQL.
- Experience with Machine Learning and Predictive Modelling, including feature
  engineering, model evaluation, and validation of spatially autocorrelated data.
- Experience with Data Science and Analytics using Python, Pandas and GeoPandas,
  data cleaning and integration, and statistical analysis.
- Familiarity with household survey microdata, for example DHS, MICS, LSMS, or
  Multi-Tier Framework surveys.
- Knowledge of off-grid solar markets and distribution models, including solar
  home systems, pico-solar, and results-based financing.
- Dashboard and mapping development skills.

## Person of contact supporting this challenge

- Preston Adie

## Getting started

- Questions about this challenge? Join the OSEAS Discord server: <https://community.oseas.org/> — that's where you reach the case givers and mentors, before kickoff and throughout the hackathon. 
- Introduce yourself in the `#introductions` channel and join the relevant
  channels for this challenge.
- Read the documentation:
  - [Energy Access Explorer](https://www.energyaccessexplorer.org)
  - [EAE GitHub](https://github.com/energyaccessexplorer)
  - [EAE Technical Note](https://www.wri.org/research/energy-access-explorer-data-and-methods?ap3c=IGaj6AgspJqgeKwBAGaj6AgmzCZ5Iv70Fr7H6ahniwtFr1FOgg)
