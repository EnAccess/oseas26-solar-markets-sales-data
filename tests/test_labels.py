import copy
import json

import numpy as np
import pandas as pd
import pytest

from solar_markets import labels as L
from solar_markets.config import DEFAULT_CONFIG, PROJECT_ROOT, load_config

CFG = load_config(DEFAULT_CONFIG)
CENSUS = CFG["labels"]["census"]


def persons_frame():
    # Two sectors. Household 1 (solar, 3 members), 2 (grid, 2 members), 3 (flashlight, 1 member),
    # 4 (missing answer). Weights differ to check weighting.
    return pd.DataFrame({
        "household_id":   [1, 1, 1, 2, 2, 3, 4],
        "sector":         [1101, 1101, 1101, 1101, 1101, 1102, 1102],
        "urban":          [1, 1, 1, 1, 1, 2, 2],
        "lighting":       [3, 3, 3, 1, 1, 11, 99],
        "grid_connected": [2, 2, 2, 1, 1, 2, 2],
        "weight":         [10.0, 10.0, 10.0, 30.0, 30.0, 10.0, 10.0],
    })


def test_to_households_keeps_one_row_per_household_with_size():
    hh = L.to_households(persons_frame())
    assert len(hh) == 4
    assert dict(zip(hh["household_id"], hh["household_size"])) == {1: 3, 2: 2, 3: 1, 4: 1}


def test_classify_lighting_groups_and_missing():
    codes = pd.Series([1, 3, 4, 11, 2, 99])
    groups = L.classify_lighting(codes, CENSUS).tolist()
    assert groups[:5] == ["grid", "solar", "solar", "unserved", "other"]
    assert pd.isna(groups[5])


def test_aggregate_shares_are_weighted_and_sum_to_one():
    hh = L.to_households(persons_frame())
    hh["group"] = L.classify_lighting(hh["lighting"], CENSUS)
    out = L.aggregate_shares(hh, "sector_code").set_index("sector_code")

    # Sector 1101: solar weight 10, grid weight 30 -> 25% solar, 75% grid.
    assert out.loc[1101, "solar_share"] == pytest.approx(0.25)
    assert out.loc[1101, "grid_share"] == pytest.approx(0.75)
    # Sector 1102: household 4 has a missing answer and is excluded.
    assert out.loc[1102, "n_households_sample"] == 1
    assert out.loc[1102, "unserved_share"] == pytest.approx(1.0)
    shares = out[[f"{g}_share" for g in L.GROUPS]].sum(axis=1)
    assert np.allclose(shares, 1.0)


def test_national_summary_household_size_is_weighted():
    hh = L.to_households(persons_frame())
    hh["group"] = L.classify_lighting(hh["lighting"], CENSUS)
    s = L.national_summary(hh)
    assert s["solar_share"] == pytest.approx(10 / 50)
    # sizes 3, 2, 1, 1 with weights 10, 30, 10, 10
    assert s["avg_household_size"] == pytest.approx((30 + 60 + 10 + 10) / 60)


def test_norm_name():
    assert L.norm_name("  Nyamirambo ") == "nyamirambo"
    assert L.norm_name("Gikondo-Kicukiro") == "gikondo kicukiro"


BOUNDARIES = PROJECT_ROOT / "data" / "raw" / "boundaries"


@pytest.mark.skipif(not (BOUNDARIES / "geoBoundaries-RWA-ADM3.geojson").exists(),
                    reason="boundary files not downloaded")
def test_run_end_to_end_on_synthetic_census(tmp_path):
    reference = pd.read_csv(PROJECT_ROOT / CFG["labels"]["reference"])
    rng = np.random.default_rng(0)
    rows = []
    for i, code in enumerate(reference["sector_code"]):
        for j in range(20):
            hid = code * 10_000 + j
            for _ in range(int(rng.integers(1, 6))):
                rows.append({"ml03": code, "ml07": 2, "hhid": hid, "h15": int(rng.choice([1, 3, 11])),
                             "h14": 2, "HH_weight": 10.0})
    census_dir = tmp_path / "census"
    census_dir.mkdir()
    pd.DataFrame(rows).to_csv(census_dir / "synthetic.csv", index=False)

    cfg = copy.deepcopy(CFG)
    cfg["labels"]["census"]["folder"] = str(census_dir)
    cfg["paths"].update(raw=str(PROJECT_ROOT / "data" / "raw"), processed=str(tmp_path / "processed"),
                        reports=str(tmp_path / "reports"))
    for p in ("processed", "reports"):
        (tmp_path / p).mkdir()

    L.run(cfg)

    import geopandas as gpd

    out = gpd.read_file(tmp_path / "processed" / "labels.gpkg")
    assert len(out) == 416
    assert out["solar_share"].notna().all()
    assert out["sector_code"].is_unique
    summary = json.loads((tmp_path / "reports" / "labels_summary.json").read_text())
    assert 0 < summary["solar_share"] < 1
