"""Documentation content served by the API. Live status, licence and dates are merged in from
data/processed/<CODE>/meta.json by /api/data-sources, so the page reflects what was actually loaded."""

DATA_SOURCES = [
    {
        "id": "population", "meta_key": "population", "name": "WorldPop population (2020, 1 km)",
        "description": "Unconstrained people-per-pixel estimates, summed onto the 5 km analysis grid.",
        "resolution": "~1 km, summed to 5 km cells",
        "role": "Population and population density; energy-need input",
        "limitations": "Modelled estimate for 2020; cells partly outside Rwanda or over water are underestimated.",
    },
    {
        "id": "night_lights", "meta_key": "night_lights", "name": "NASA Black Marble VNP46A2 nighttime lights",
        "description": "VIIRS day/night band radiance sampled at each cell centre from NASA LAADS.",
        "resolution": "~500 m, sampled at the cell centre",
        "role": "Darkness component of energy need (a grid-electricity proxy only)",
        "limitations": "Single-day sample; cannot detect solar home systems or lanterns. Dark does not mean no solar.",
    },
    {
        "id": "grid", "meta_key": "grid", "name": "OpenStreetMap power infrastructure",
        "description": "Mapped power lines, minor lines, cables, substations and plants via the Overpass API.",
        "resolution": "Vector lines and points",
        "role": "Distance to mapped grid, grid presence, infrastructure overlay",
        "limitations": "Volunteer-mapped and incomplete; a mapped line is not proof of a household connection.",
    },
    {
        "id": "survey", "meta_key": "survey", "name": "MTF household survey: solar device module",
        "description": "Survey records for households owning a solar device, with nationally representative weights.",
        "resolution": "District (no household GPS)",
        "role": "Solar uptake evidence used in the market-gap score",
        "limitations": "Lists solar owners only, so shares need a population denominator; 2-47 sampled solar "
                       "households per district; survey year not recorded in the file.",
    },
    {
        "id": "relative_wealth", "meta_key": "relative_wealth", "name": "Meta Relative Wealth Index",
        "description": "Relative wealth estimated from satellite imagery and connectivity data.",
        "resolution": "2.4 km tiles, averaged per cell",
        "role": "Context indicator (affordability); not part of the score",
        "limitations": "Relative, not absolute; modelled; cells without a tile centre have no value.",
    },
    {
        "id": "districts", "meta_key": "districts", "name": "GADM administrative boundaries",
        "description": "District and province polygons used to name cells and attach survey statistics.",
        "resolution": "District polygons",
        "role": "Location names, district survey join",
        "limitations": "A 5 km cell is assigned to the district containing its centre; cells are not villages.",
    },
    {
        "id": "surveys_gps", "meta_key": "surveys", "name": "Georeferenced survey clusters (DHS / MICS / MTF)",
        "description": "Cluster-level solar ownership with displaced GPS, needed to train the penetration model.",
        "resolution": "Survey cluster (displaced GPS point)",
        "role": "Model training labels",
        "limitations": "Not in the repository; requires registration with the survey programme.",
    },
    {
        "id": "minigrids", "meta_key": "minigrids", "name": "Existing minigrid locations",
        "description": "Verified operating minigrid sites.",
        "resolution": "Points / polygons",
        "role": "Infrastructure overlay and model feature",
        "limitations": "No verified dataset is in the repository; candidate-site datasets are not used as existing minigrids.",
    },
    {
        "id": "solar_resource", "meta_key": "solar_resource", "name": "Global Solar Atlas (GHI)",
        "description": "Long-term average global horizontal irradiation.",
        "resolution": "~1 km",
        "role": "Model feature only",
        "limitations": "Not supplied in this checkout.",
    },
    {
        "id": "gogla", "meta_key": "gogla", "name": "GOGLA sales data",
        "description": "Aggregated national sales of off-grid solar products.",
        "resolution": "National",
        "role": "National control total / sanity check only (never a pixel-level label)",
        "limitations": "Not supplied in this checkout; covers affiliated companies only.",
    },
]

LIMITATIONS = [
    "Nighttime darkness indicates limited grid electricity, not the absence of solar products.",
    "Mapped OpenStreetMap infrastructure is incomplete, and a mapped line does not mean households are connected.",
    "Solar uptake evidence is district-level (MTF survey) with small samples; it cannot distinguish villages "
    "or 5 km cells within a district.",
    "The district solar share divides survey-weighted households by WorldPop population and an assumed "
    "household size, so it mixes years and sources.",
    "The market opportunity score is a relative 0-100 ranking for field investigation, not a percentage of "
    "households and not evidence of commercial viability.",
    "No georeferenced survey labels are available, so the penetration model cannot be trained on real data; "
    "the stored model (trained on synthetic data) is not used.",
    "Night-light values are a single-day VNP46A2 sample and can be affected by clouds, moonlight and fires.",
    "Population is a 2020 modelled estimate; cells partly outside Rwanda or over water are underestimated.",
    "Results should be validated with field data and national electrification programme records.",
]
