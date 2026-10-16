# Architecture

```
data/raw/RW/ (gitignored)                 scripts/ingest/fetch_population_wealth.py   WorldPop, Meta RWI
  population.tif, relative_wealth.csv     scripts/update_grid_from_overpass.py        OSM power infrastructure
  grid.geojson, power_facilities.geojson  scripts/ingest + process (night lights)      NASA VNP46A2 cache
        |
pipeline/build.py  (python -m app.pipeline.build)
  ingestion.py          load real inputs; missing ones stay missing (no synthetic fallback)
  feature_engineering   distance to grid, grid presence, settlement density
  cleaning.py           validate + clip, never impute
  build.join_nightlights_cache   NASA cache joined by cell_id with a coordinate check
  survey.py             GADM district/province + MTF district survey indicators
        |
data/processed/RW/cells_features.csv + meta.json (provenance)  + infrastructure.geojson   (committed)
        |
services/data_service.py   load once, reload on file change, merge usable model outputs,
                           apply services/market_gap.py (single scoring implementation)
services/map_service.py    cached GeoJSON layers (warmed at startup)
services/prediction_service.py, indicators.py   cell evidence, interpretation, statistics
services/location_service.py   cell ID / coordinates / district / province lookup
services/report_service.py + report_pdf.py      JSON / CSV / PDF reports
services/assistant_service.py  Claude tool-use loop over the services above (read-only tools)
        |
api/  FastAPI routers (layers, cells, grid, models, statistics, reports, assistant)
        |
frontend/  React + Vite + React-Leaflet: Explorer, About, Data sources, Model, Limitations
```

- **One grid.** 5 km lat/lon cells (`GRID_RESOLUTION_KM`); `cell_id` is the stable key across all files.
- **No network at request time.** The API serves processed files only; refresh scripts are run explicitly.
- **EAE-ready.** Read-only JSON/GeoJSON endpoints; values are documented with unit, direction and source.
- **Demo mode** (`DEMO_MODE=true`) still generates a fully synthetic dataset for pipeline testing; it is
  labelled synthetic everywhere and is not the default.
