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
| Rwanda Population and Housing Census 2022 (PHC5), household file | `data/raw/census/` | Register on the [NISR microdata portal](https://microdata.statistics.gov.rw/index.php/catalog/109), "Get Microdata" | NISR microdata release policy; do not redistribute |
| Rwanda DHS 2019-20: household recode (HR) + GPS (GE) | `data/raw/dhs/` | Request at [dhsprogram.com](https://dhsprogram.com/data/new-user-registration.cfm) (survey + GPS datasets) | DHS terms; do not redistribute |
| Administrative boundaries ADM1-ADM3 | `data/raw/boundaries/` | [geoBoundaries](https://www.geoboundaries.org/) (RWA) | CC BY 4.0 / ODbL (check per file) |
| Meta Relative Wealth Index (Rwanda CSV) | `data/raw/rwi/` | [Humanitarian Data Exchange](https://data.humdata.org/), search "relative wealth index" | CC BY 4.0 |
| Gridfinder predicted grid lines | `data/raw/grid/` | [gridfinder.org](https://gridfinder.org/) (Zenodo download) | CC BY 4.0 |
| Night lights, population, travel time, land cover | pulled by `features.py` | Google Earth Engine (no manual download) | See each Earth Engine catalogue page |
| GOGLA sales reports (control total) | `data/raw/gogla/` | [GOGLA market reports](https://gogla.org/reports/) | Public reports; cite |

Earth Engine datasets used:

- `NOAA/VIIRS/DNB/ANNUAL_V22`: VIIRS annual night lights
- `WorldPop/GP/100m/pop`: WorldPop population
- `Oxford/MAP/accessibility_to_cities_2015_v1_0`: travel time to cities
- `ESA/WorldCover/v200`: land cover (built-up share)
