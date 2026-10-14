import copy
import json

import pandas as pd
import pytest

from solar_markets import validate as V
from solar_markets.config import DEFAULT_CONFIG, load_config

CFG = load_config(DEFAULT_CONFIG)


def households():
    # District 11: solar (w 2), grid (w 1), candle (w 1). District 12: solar (w 1), grid (w 3).
    return pd.DataFrame({
        "district_code": [11, 11, 11, 12, 12],
        "weight": [2.0, 1.0, 1.0, 1.0, 3.0],
        "group": ["solar", "grid", "none", "solar", "grid"],
    })


def test_weighted_shares_by_district_and_national():
    by = V.weighted_shares(households(), "district_code").set_index("district_code")
    assert by.loc[11, "dhs_solar"] == pytest.approx(0.5)
    assert by.loc[11, "dhs_none"] == pytest.approx(0.25)
    assert by.loc[12, "dhs_grid"] == pytest.approx(0.75)
    nat = V.weighted_shares(households()).iloc[0]
    assert nat["dhs_solar"] == pytest.approx(3 / 8)


def test_agreement_statistics():
    df = pd.DataFrame({"ours": [0.1, 0.2, 0.3], "dhs": [0.2, 0.3, 0.4]})
    a = V.agreement(df, "ours", "dhs")
    assert a["pearson_r"] == pytest.approx(1.0)
    assert a["mae_pp"] == pytest.approx(10.0)
    assert a["mean_diff_pp"] == pytest.approx(-10.0)


def test_run_end_to_end_on_synthetic_dhs_file(tmp_path):
    pyreadstat = pytest.importorskip("pyreadstat")
    cfg = copy.deepcopy(CFG)
    cfg["paths"] = {k: str(tmp_path / k) for k in cfg["paths"]}
    for k in cfg["paths"]:
        (tmp_path / k).mkdir()
    dcfg = cfg["validation"]["dhs"]
    dcfg["household_file"] = "dhs.dta"
    cols = dcfg["columns"]
    # hv262: 1 = electricity, 2 = solar, 14 = candle; weights with 6 implied decimals.
    hh = pd.DataFrame({cols["district"]: [11, 11, 11, 12, 12, 12],
                       cols["weight"]: [1e6] * 6,
                       cols["light"]: [2, 2, 1, 1, 1, 14]})
    pyreadstat.write_dta(hh, str(tmp_path / "raw" / "dhs.dta"))
    pd.DataFrame({"district_code": [11, 12], "district": ["A", "B"], "solar_share": [0.5, 0.1],
                  "grid_share": [0.3, 0.6], "unserved_share": [0.2, 0.3]}).to_csv(
        tmp_path / "processed" / "labels_district.csv", index=False)

    V.run(cfg)

    table = pd.read_csv(tmp_path / "reports" / "dhs_validation.csv").set_index("district_code")
    assert table.loc[11, "dhs_solar"] == pytest.approx(2 / 3)
    assert table.loc[12, "dhs_none"] == pytest.approx(1 / 3)
    summary = json.loads((tmp_path / "reports" / "dhs_validation.json").read_text())
    assert summary["households"] == 6
    assert summary["national"]["solar"] == pytest.approx(2 / 6)
    assert (tmp_path / "reports" / "dhs_validation.png").exists()
