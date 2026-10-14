# Data

Raw and intermediate data are **not** committed (licences and size). Each teammate downloads
them into the folders below. Only code, aggregated outputs and metadata go to GitHub.

```
data/
  raw/         downloads exactly as received
  interim/     cleaned tables, Earth Engine exports
  processed/   labels.gpkg, feature_stack.tif, train_table.csv
```

## Where each dataset goes

| Dataset | Save to | How to get it | Licence / terms |
| --- | --- | --- | --- |
| Rwanda Population and Housing Census 2022 (PHC5), `PHC5_Public_microdata_2022` (one row per person, ~10% sample; Stata, SPSS or CSV) | `data/raw/census/` | Register on the [NISR microdata portal](https://microdata.statistics.gov.rw/index.php/catalog/109), "Get Microdata" | NISR microdata release policy; do not redistribute |
| Rwanda DHS 2019-20: household recode (HR) + GPS (GE) | `data/raw/dhs/` | Request at [dhsprogram.com](https://dhsprogram.com/data/new-user-registration.cfm) (survey + GPS datasets) | DHS terms; do not redistribute |
| Districts (ADM2) and sectors (ADM3): `geoBoundaries-RWA-ADM2.geojson`, `geoBoundaries-RWA-ADM3.geojson` | `data/raw/boundaries/` | [geoBoundaries gbOpen RWA](https://www.geoboundaries.org/) (source: Open Data Rwanda, 2012 boundaries, 416 sectors) | CC BY 4.0 |
| Meta Relative Wealth Index: `rwa_relative_wealth_index.csv` (3,715 points, ~2.4 km) | `data/raw/rwi/` | [Humanitarian Data Exchange](https://data.humdata.org/dataset/relative-wealth-index) | **CC BY-NC 4.0** (non-commercial); cite Chi et al., PNAS 2022, doi:10.1073/pnas.2113658119 |
| Gridfinder predicted grid lines: `grid.gpkg` (global, 725 MB), clipped to `gridfinder_rwa.gpkg` | `data/raw/grid/` | [Zenodo record 3628142](https://zenodo.org/records/3628142) (Arderne et al., 2020) | CC BY 4.0 |
| Night lights, population, travel time, land cover | pulled by `features.py` | Google Earth Engine (no manual download) | See each Earth Engine catalogue page |
| GOGLA sales reports (control total) | `data/raw/gogla/` | [GOGLA market reports](https://gogla.org/reports/) | Public reports; cite |

Earth Engine datasets used:

- `NOAA/VIIRS/DNB/ANNUAL_V22`: VIIRS annual night lights
- `WorldPop/GP/100m/pop`: WorldPop population
- `Oxford/MAP/accessibility_to_cities_2015_v1_0`: travel time to cities
- `ESA/WorldCover/v200`: land cover (built-up share)

Small lookup tables that are safe to commit live in [`reference/`](reference/README.md).
