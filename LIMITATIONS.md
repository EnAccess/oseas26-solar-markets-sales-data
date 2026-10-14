# What this model cannot see

This page covers the two Rwanda layers in `outputs/` (off-grid solar penetration and underserved
solar market, version 0.1). Numbers marked `__` are filled in from the pipeline reports after a
full run. The file each one comes from is given in brackets.

## 1. What it measures, and what it doesn't

- It estimates the share of households whose **main** lighting source is off-grid solar
  (standalone solar system or private solar mini-grid; census 2022, question h15). Households
  that own a solar lantern but mainly use something else are not counted.
- It says nothing about system size, quality or whether systems still work. A broken solar
  home system still counts as "served" if the household reported it as its main light.
- It covers households only. Productive use (pumps, mills, shops, clinics) is not measured.
- "Underserved" means households with neither grid nor solar as their main light. It does not
  measure ability or willingness to pay.

## 2. Where it will be wrong

- **Inside a sector.** Labels are sector averages (416 sectors). The model never sees a single
  village, so a poor village inside a better-off sector is averaged away, and the 1 km
  pixels can be smoother or more extreme than reality. Pixel predictions re-aggregated to
  sectors differ from the census by __ pp on average [`reports/reaggregation.csv`].
- **In districts it has not seen.** With whole districts held out, the error is __ pp on average
  (R² __), against __ pp with random splits [`reports/cv_results.csv`]. The district check after
  calibration is worst in __ (__ pp) [`reports/calibration.json`]. Predictions there deserve
  less trust.
- **Places unlike any sector:** national parks, wetlands, refugee camps, new settlements built
  after 2022.
- **Places that changed since 2022:** grid extensions and solar campaigns after the census are
  not in the labels.

## 3. Blind spots in the inputs

- Night lights cannot see dim indoor solar lighting. That is why this layer exists, but it also
  means the model leans on proxies (wealth, remoteness, grid distance) rather than direct evidence.
- Inputs come from different years: census 2022, VIIRS 2022, WorldPop 2020, Meta RWI ~2021,
  Gridfinder 2020, travel time 2015.
- The Relative Wealth Index is itself a model estimate, with its own error, and we use the
  nearest point (~2.4 km apart).
- Gridfinder predicts where lines are from night lights and roads. It can miss new or
  low-voltage lines, or include lines that were never built.
- Population grids can misplace rural people, which shifts household counts in the
  underserved layer.
- Calibration currently uses the census national share, the same source as the labels. So it
  fixes the level of the 1 km map; it is not an independent check. GOGLA sales are the planned
  independent control total.

## 4. Who it might misallocate capital toward or away from

- **Away from** the poorest households in sectors that look served on average.
- **Toward** areas where solar was sold but systems have since failed or been repossessed:
  they look served, so money may skip them when it should not, or flow to the wrong
  neighbours.
- **Away from or toward** areas the grid is about to reach. The model cannot see grid plans,
  so it may prioritise solar where the grid arrives next year, or the reverse.
- **Toward dense areas.** The underserved layer counts households, so populous sectors rank
  above remote ones with a higher unserved *share* but fewer people.
- **Away from** groups the census or population grids undercount: informal settlements,
  mobile and refugee populations.

## 5. How to use it responsibly

- Use it to **shortlist** sectors for field verification (`reports/top_underserved_sectors.csv`),
  not to make final funding decisions.
- Combine it with local knowledge: REG/EDCL grid plans, company coverage, district officials.
- Prefer areas where the model and the census agree. Check each priority zone's drivers in the
  map popup before acting on it.
- Commercial use is restricted: the layers are CC BY-NC 4.0 because the wealth index input is.
- Re-run with newer survey data when available (EICV7, the next DHS, MTF), and with GOGLA
  calibration.
