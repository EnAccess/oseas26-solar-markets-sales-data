# Data sources

Live status, dates and licences are served by `GET /api/data-sources` (content in
`backend/app/data_sources.py`, provenance from `backend/data/processed/RW/meta.json`).

| Input | File | Obtained by | Licence | Used for |
|---|---|---|---|---|
| WorldPop 2020 1 km (ppp) | `data/raw/RW/population.tif` | `scripts/ingest/fetch_population_wealth.py` | CC BY 4.0 | population, density, need score |
| Meta Relative Wealth Index | `data/raw/RW/relative_wealth.csv` | same script (HDX) | CC BY-NC 4.0 | context indicator |
| OSM power lines / substations / plants | `data/raw/RW/grid.geojson`, `power_facilities.geojson` | `scripts/update_grid_from_overpass.py` | ODbL 1.0 | distance to grid, grid presence, overlay |
| NASA VNP46A2 radiance | `data/processed/RW/cells_with_nightlights.csv` | `scripts/schedule/weekly_nightlights.ps1` (`NASA_EARTHDATA_TOKEN`) | NASA open data | darkness component |
| MTF solar device module | `data/processed/RW/Household_Solar_Device_Use_and_Ownership.csv` | checked in | see survey terms | district solar uptake |
| GADM districts | `data/processed/RW/rwanda_districts.geojson` | checked in | GADM licence | names, survey join |

Optional inputs that are read when present in `data/raw/RW/` but are **not** in the repository:
`surveys.csv` (GPS survey clusters: `latitude, longitude, solar_ownership[, n_households]`, model labels),
`night_lights.tif`, `solar_resource.tif` (GHI), `minigrids.geojson` (verified sites only), `gogla.csv`
(`country, reported_sales, product_category, year`). Missing inputs stay missing; nothing is substituted.
