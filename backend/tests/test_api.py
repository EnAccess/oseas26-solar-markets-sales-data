"""API behaviour over the real processed dataset, including cross-endpoint consistency."""
import io

import pandas as pd
import pytest

CELL = "RW_0500"


def test_health_and_meta(client):
    assert client.get("/api/health").json() == {"status": "ok"}
    meta = client.get("/api/meta").json()
    assert meta["is_demo"] is False
    assert meta["model_status"]["usable"] is False  # stored model was trained on synthetic labels
    assert meta["selected_model"] == "not_available"
    assert "1 - solar_uptake" in meta["method"]["formula"]


def test_layer_selector_hides_redundant_layers(client):
    layers = {l["id"]: l for l in client.get("/api/layers").json()}
    assert layers["population_total"]["selector"] is False
    assert "solar_penetration" not in layers  # no usable model predictions
    assert {"market_gap", "population", "night_lights", "grid", "survey_solar"} <= {
        k for k, v in layers.items() if v["selector"]}


def test_unknown_layer_and_cell(client):
    assert client.get("/api/map/layer/nope").status_code == 404
    assert client.get("/api/cells/RW_9999").status_code == 404
    assert client.get("/api/cells/XX_0001").status_code == 404


def test_population_layer_metadata_and_missing_cells(client):
    layer = client.get("/api/map/layer/population").json()
    meta = layer["metadata"]
    assert meta["unit"] == "people/km²" and meta["scale"] == "log"
    assert "WorldPop" in meta["source"] and meta["source_date"] == "2020"
    values = [f["properties"]["value"] for f in layer["features"]]
    assert len(values) == meta["n_cells"]
    assert sum(v is None for v in values) == meta["n_missing"] > 0


def test_values_agree_across_map_cell_report_and_csv(client):
    cell = client.get(f"/api/cells/{CELL}").json()
    indicators = {i["key"]: i for i in cell["indicators"]}

    def layer_value(layer_id):
        layer = client.get(f"/api/map/layer/{layer_id}").json()
        return next(f["properties"]["value"] for f in layer["features"] if f["properties"]["cell_id"] == CELL)

    assert layer_value("population") == indicators["population_density"]["display_value"]
    assert layer_value("night_lights") == indicators["nighttime_radiance"]["display_value"]
    assert layer_value("market_gap") == indicators["market_gap_score"]["display_value"]
    assert round(cell["market_gap_score"] * 100) == cell["opportunity_score"]

    report = client.post("/api/reports/summary", json={"cell_ids": [CELL]}).json()
    entry = report["cells"][0]
    assert entry["opportunity_score"] == cell["opportunity_score"]
    assert entry["indicators"]["population_density"]["value"] == cell["population_density"]

    csv = pd.read_csv(io.StringIO(client.post("/api/reports/csv", json={"cell_ids": [CELL]}).text))
    assert csv.loc[0, "Population density (people/km²)"] == indicators["population_density"]["display_value"]


def test_cell_without_survey_evidence_has_no_score(client):
    cell = client.get("/api/cells/RW_0002").json()
    assert cell["district"] is None
    assert cell["opportunity_score"] is None and cell["evidence_level"] == "insufficient"
    assert "Solar uptake evidence" in cell["missing_inputs"]
    assert "missing evidence is not evidence" in cell["interpretation"]


def test_score_is_never_labelled_as_household_percentage(client):
    meta = client.get("/api/map/layer/market_gap").json()["metadata"]
    assert meta["unit"] == "score 0–100"
    assert "not a percentage" in meta["description"]


def test_infrastructure_is_classified_osm_data(client):
    infra = client.get("/api/map/infrastructure").json()
    kinds = infra["metadata"]["counts"]
    assert kinds.get("grid_line", 0) > 0 and kinds.get("substation", 0) > 0
    assert "minigrid" not in kinds  # no verified minigrid dataset
    lines = [f for f in infra["features"] if f["properties"]["kind"] == "grid_line"]
    assert all(f["properties"]["line_class"] in {"line", "minor_line", "cable"} for f in lines)
    assert all(f["properties"].get("osm_id") for f in lines)
    assert "does not mean" in infra["metadata"]["caveat"]


def test_statistics_threshold_validation(client):
    s = client.get("/api/statistics", params={"threshold": 0.55}).json()
    assert 0 < s["potentially_underserved_cells"] <= s["n_scored_cells"] < s["n_cells"]
    assert s["avg_predicted_penetration"] is None
    assert client.get("/api/statistics", params={"threshold": 2}).status_code == 422


def test_data_sources_report_status(client):
    sources = {s["id"]: s for s in client.get("/api/data-sources").json()}
    assert sources["population"]["status"] == "real" and sources["population"]["licence"] == "CC BY 4.0"
    assert sources["minigrids"]["status"] == "missing"
    assert sources["surveys_gps"]["status"] == "missing"


def test_model_performance_flags_synthetic_training(client):
    r = client.get("/api/model/performance")
    if r.status_code == 404:  # no metrics in a fresh checkout (models/ is gitignored)
        return
    body = r.json()
    assert body["usable"] is False and "SYNTHETIC" in body["note"]


@pytest.mark.parametrize("query,kind,name", [
    ("Nyagatare", "district", "Nyagatare"),
    ("nyagatre", "district", "Nyagatare"),
    ("Eastern Province", "province", "Eastern Province"),
    ("kigali", "province", "Kigali City"),
    ("rw_0001", "grid", "Cyembogo, Matimba"),
    ("-1.95, 30.06", "grid", None),
])
def test_location_search_matches(client, query, kind, name):
    r = client.get("/api/locations/search", params={"q": query}).json()
    assert r["matched"] and r["type"] == kind and r["cell_ids"]
    if name:
        assert r["name"] == name


@pytest.mark.parametrize("query", ["Gikomero village", "Paris", "0, 0", "RW_9999"])
def test_location_search_explains_unmatched(client, query):
    r = client.get("/api/locations/search", params={"q": query}).json()
    assert r["matched"] is False and r["note"]


def test_model_raster_not_served_from_unusable_model(client):
    assert client.get("/api/raster/metadata").status_code == 503
    assert client.get("/api/raster/solar_penetration.tif").status_code == 503


def test_grid_check_counts_osm_classes(client):
    r = client.get("/api/grid/check", params={"lat": -1.95, "lon": 30.06, "radius_km": 10}).json()
    counts = r["metadata"]["counts"]
    assert counts["lines"] > 0 and counts["substations"] > 0 and counts["minigrids"] == 0
    assert all(f["properties"]["kind"] in {"grid_line", "substation", "plant"} for f in r["features"])


def test_place_names_are_unique_and_searchable(client, svc):
    cells = svc.cells("RW")
    assert cells["place_name"].is_unique and cells["place_name"].notna().all()
    layer = client.get("/api/map/layer/population").json()
    assert all(f["properties"]["name"] for f in layer["features"])
    r = client.get("/api/locations/search", params={"q": "Cyembogo"}).json()
    assert r["matched"] and r["type"] == "cell" and "RW_0001" in r["cell_ids"]
