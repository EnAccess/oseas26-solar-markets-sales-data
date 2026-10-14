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

---

## Our solution (work in progress)

We are building the market-reality layer for **Rwanda** at 1 km resolution:

1. **Labels:** share of households using off-grid solar for lighting, from the Rwanda
   Population and Housing Census 2022 (sector level), upgraded later to DHS 2019-20 GPS clusters.
2. **Features:** VIIRS night lights, WorldPop population, Meta Relative Wealth Index,
   distance to grid (Gridfinder), travel time to cities and built-up share.
3. **Model:** LightGBM, with random and blocked (by district) cross-validation and SHAP
   feature analysis framed as hypotheses.
4. **Calibration:** logit shift so the national total matches a control total (census now,
   GOGLA sales next).
5. **Outputs:** two EAE-conformant 0-1 rasters (off-grid solar penetration, underserved
   market) with metadata, a limitations statement and an interactive map.

### Features

`python -m solar_markets.features` builds `data/processed/feature_stack.tif`: one band per
feature on a 30 arc-second grid (~0.93 km, EPSG:4326, 258 x 228 pixels over Rwanda), NaN
outside the country. Earth Engine bands are aggregated on the server onto exactly this grid
and cached in `data/interim/ee_stack.tif`.

| Band | Meaning | Source | Year | Native resolution | Aggregation to 1 km | Model transform | Licence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `ntl` | night-time radiance (nW/cm²/sr) | VIIRS annual V2.2 (`NOAA/VIIRS/DNB/ANNUAL_V22`, band `average`) | 2022 | ~460 m | mean | log1p | CC BY 4.0 (EOG) |
| `pop` | people per pixel | WorldPop (`WorldPop/GP/100m/pop`) | 2020 | 100 m | sum | log1p | CC BY 4.0 |
| `travel_min` | minutes to the nearest city | Oxford MAP (`Oxford/MAP/accessibility_to_cities_2015_v1_0`) | 2015 | ~1 km | mean | log1p | CC BY 4.0 |
| `built` | share of built-up land | ESA WorldCover v200, class 50 (`ESA/WorldCover/v200`) | 2021 | 10 m | mean | none | CC BY 4.0 |
| `rwi` | Relative Wealth Index | Meta RWI (HDX) | 2021 | ~2.4 km points | nearest point | none | CC BY-NC 4.0 |
| `dist_grid` | km to the nearest grid line | Gridfinder (Zenodo 3628142) | 2020 | vector | distance from pixel centre | log1p | CC BY 4.0 |

Distance to the grid is measured on a raster padded by 30 km, so lines just across the border
count. The training table (`data/processed/train_table.csv`, one row per sector) holds the
**population-weighted mean** of each band inside the sector (plain mean for `pop`), so the
features describe where people live rather than empty land. Sectors smaller than one pixel take
the pixel under their centre. A quick-look of every band is saved to `reports/feature_bands.png`.

### Development setup

**Option A: conda (recommended on Windows)**

```bash
conda env create -f environment.yml
conda activate solar-markets
```

**Option B: pip + venv (Python 3.10+)**

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows (macOS/Linux: source .venv/bin/activate)
pip install -e ".[dev]"
```

Then:

```bash
cp .env.example .env                           # set GEE_PROJECT to your Earth Engine project
python -m solar_markets.check_setup            # libraries, config, folders
python -m solar_markets.check_setup --gee      # also connects to Earth Engine
pytest
```

Download the input data as described in [`data/README.md`](data/README.md). Survey microdata
must never be committed.

### Running the pipeline

Each stage reads `config.yml` and writes one output that the next stage reads:

```bash
python -m solar_markets.labels     # data/processed/labels.gpkg
python -m solar_markets.features   # data/processed/feature_stack.tif, train_table.csv
python -m solar_markets.model      # reports/cv_results.csv, outputs/solar_share_pred.tif
python -m solar_markets.calibrate  # outputs/solar_share_calibrated.tif
python -m solar_markets.export     # outputs/rwa_ogs_*.tif + .yml metadata
python -m solar_markets.webmap     # docs/map.html
```

### Repository layout

```
config.yml               country, year, resolution, features, model settings
src/solar_markets/       one module per pipeline stage + config and setup check
tests/                   config tests; EAE conformance tests for exported layers
data/                    raw / interim / processed (git-ignored, see data/README.md)
outputs/                 final rasters and metadata
reports/                 cross-validation results and figures
docs/                    interactive map (GitHub Pages)
```
