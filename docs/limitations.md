# Limitations

The authoritative list is `LIMITATIONS` in `backend/app/data_sources.py` (served at `/api/limitations`,
shown on the Limitations page and in every report).

- Darkness indicates limited grid electricity, not the absence of solar products.
- Mapped OSM infrastructure is incomplete; a mapped line does not mean households are connected.
- Solar uptake evidence is district-wide (MTF, 2-47 sampled solar households per district, year unknown).
- The district share mixes survey weights, WorldPop 2020 population and an assumed household size of 4.3.
- The opportunity score is a relative ranking, not a percentage of households or proof of viability.
- No georeferenced survey labels exist in the repository, so no validated penetration model is in use.
- Night lights are a single-day VNP46A2 sample.
- Border and lake cells have missing or under-counted population; 204 border cells have no district.

## Who it could misallocate capital toward

- Districts whose small survey sample under-records solar (their cells score too high).
- Peri-urban cells near mapped but unreliable or unconnected lines (their remoteness is understated, so
  they score too low).
- Dense, dark cells inside districts with high average ownership, where pockets without solar are hidden
  by the district mean.
