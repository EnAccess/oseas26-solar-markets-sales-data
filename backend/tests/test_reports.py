"""Selected-location reports: validation, content and file formats."""
import io

import pandas as pd

from app.services import report_service

IDS = ["RW_0500", "RW_0501", "RW_0002"]


def test_report_contains_only_selected_cells(client):
    report = client.post("/api/reports/summary", json={"cell_ids": IDS + ["RW_0500"]}).json()
    assert [c["cell_id"] for c in report["cells"]] == IDS  # duplicates removed, order kept
    assert report["summary"]["n_cells"] == 3
    assert report["summary"]["area_km2"] == 75.0


def test_report_sections_and_provenance(client):
    report = client.post("/api/reports/summary", json={"cell_ids": IDS}).json()
    assert {"title", "generated_at", "cells", "summary", "method", "sources", "interpretation", "limitations"} <= set(report)
    assert {s["key"] for s in report["sources"]} >= {"population", "night_lights", "grid", "survey"}
    assert any("no score" in line for line in report["interpretation"])
    for cell in report["cells"]:
        for record in cell["indicators"].values():
            assert {"value", "unit", "source", "status", "kind"} <= set(record)


def test_report_validation_errors(client):
    assert client.post("/api/reports/summary", json={"cell_ids": []}).status_code == 422
    r = client.post("/api/reports/summary", json={"cell_ids": ["RW_0500", "RW_9999"]})
    assert r.status_code == 422 and "RW_9999" in r.json()["detail"]
    too_many = [f"RW_{i:04d}" for i in range(1, report_service.MAX_REPORT_CELLS + 2)]
    assert client.post("/api/reports/summary", json={"cell_ids": too_many}).status_code == 422


def test_csv_export(client):
    r = client.post("/api/reports/csv", json={"cell_ids": IDS})
    assert r.headers["content-type"].startswith("text/csv")
    frame = pd.read_csv(io.StringIO(r.text))
    assert list(frame["analysis_cell_id"]) == IDS
    assert list(frame.columns[:3]) == ["place", "cell", "sector"]
    assert not frame["place"].str.match(r"RW_\d{4}").any()
    assert frame.loc[frame["analysis_cell_id"] == "RW_0002", "Market opportunity score (score 0–100)"].isna().all()


def test_pdf_export(client):
    r = client.post("/api/reports/pdf", json={"cell_ids": IDS})
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF") and len(r.content) > 10_000


def test_report_is_cached_per_dataset_version(svc):
    a = report_service.build_report(svc, "RW", IDS, 0.55)
    b = report_service.build_report(svc, "RW", list(reversed(IDS)), 0.55)
    assert a is report_service.build_report(svc, "RW", IDS, 0.55)
    assert {c["cell_id"] for c in b["cells"]} == set(IDS)


def test_report_uses_place_names_not_ids(client):
    report = client.post("/api/reports/summary", json={"cell_ids": ["RW_0001", "RW_0002"]}).json()
    names = [c["name"] for c in report["cells"]]
    assert names[0] == "Cyembogo, Matimba"
    assert names[1].startswith("Outside Rwanda boundary")
    assert not any("RW_0" in line for line in report["interpretation"])
