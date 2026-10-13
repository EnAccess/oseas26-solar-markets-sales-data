# Reference tables (committed)

Small lookup tables that the pipeline needs and that contain no survey microdata.

| File | Content | Source |
| --- | --- | --- |
| `rwa_sectors.csv` | 416 sector codes with sector, district and province names | Value labels of variables `ml01`, `ml02`, `ml03` in the PHC5 2022 codebook (DDI), [NISR catalogue 109](https://microdata.statistics.gov.rw/index.php/catalog/109) |
| `boundary_name_fixes.csv` | Sector names spelled differently in the geoBoundaries ADM3 file and in the census | Found by matching (district, sector) names; 415 of 416 matched without a fix |

Sector codes have four digits: the first two are the district code, the first one is the
province code (e.g. `1101` = Gitega sector, district 11 Nyarugenge, province 1 City of Kigali).
