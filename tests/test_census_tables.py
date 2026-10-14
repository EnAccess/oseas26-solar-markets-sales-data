import numpy as np
import pandas as pd
import pytest

from solar_markets import census_tables as T
from solar_markets.config import DEFAULT_CONFIG, PROJECT_ROOT, load_config

CFG = load_config(DEFAULT_CONFIG)

LIGHT_ROWS = [
    ("District and Sectors", "Percentage", "Percentage", "Total count"),
    ("District and Sectors", "Electricity", "Candles", None),
    ("Rwanda", 0.6, 0.4, 300),
    ("Nyarugenge", None, None, None),
    ("  Gitega", 0.9, 0.1, 100),
    ("Gasabo", None, None, None),
    ("  Bumbogo", 0.3, 0.7, 200),
    ("  Total", 0.6, 0.4, 300),
    ("Source: 5th Rwanda Population and Housing Census, 2022 (NISR).", None, None, None),
]


def test_sector_table_reads_districts_sectors_and_unnamed_count_column():
    df = T.sector_table(LIGHT_ROWS, "Electricity")
    assert df[["district", "sector"]].values.tolist() == [["Nyarugenge", "Gitega"],
                                                         ["Gasabo", "Bumbogo"]]
    assert df["Electricity"].tolist() == [0.9, 0.3]
    assert df["Total count"].tolist() == [100, 200]


def test_province_solar_takes_total_column():
    rows = [("Rwanda", None, None), ("  Solar power", 5, 0.14),
            ("City of Kigali", None, None), ("  Electricity from REG", 9, 0.88),
            ("  Solar power", 1, 0.016)]
    assert T.province_solar(rows) == {"Rwanda": 0.14, "City of Kigali": 0.016}


def test_split_solar_hits_province_share_and_stays_below_electrified():
    electrified = np.array([0.9, 0.5, 0.3, 0.2])
    connected = np.array([0.85, 0.3, 0.05, 0.25])
    n = np.array([100.0, 200, 300, 400])
    solar = T.split_solar(electrified, connected, n, target=0.15)
    assert (solar * n).sum() / n.sum() == pytest.approx(0.15)
    assert (solar <= electrified + 1e-12).all() and (solar >= 0).all()
    assert solar[3] == 0     # connected above electrified: no solar


def test_split_solar_caps_at_electrified_when_target_too_high():
    electrified, n = np.array([0.2, 0.4]), np.array([1.0, 1.0])
    solar = T.split_solar(electrified, np.array([0.1, 0.1]), n, target=0.9)
    assert solar == pytest.approx(electrified)


def test_match_codes_reports_unknown_sectors():
    ref = pd.DataFrame({"sector_code": [1101], "sector": ["Gitega"], "district_code": [11],
                        "district": ["Nyarugenge"], "province": ["City of Kigali"]})
    table = pd.DataFrame({"district": ["Nyarugenge"], "sector": ["Atlantis"], "x": [1]})
    with pytest.raises(ValueError, match="Atlantis"):
        T.match_codes(table, ref)


TABLES = PROJECT_ROOT / "data" / "raw" / CFG["labels"]["census_tables"]["file"]


@pytest.mark.skipif(not TABLES.exists(), reason="published census tables not downloaded")
def test_labels_from_published_tables_match_national_figures():
    reference = pd.read_csv(PROJECT_ROOT / CFG["labels"]["reference"])
    by_sector, by_district, summary, _ = T.labels_from_tables(TABLES, reference)
    assert len(by_sector) == 416 and by_sector["sector_code"].is_unique
    assert len(by_district) == 30
    # Table 8.12: 13.9% solar, 47.1% grid (electricity from REG or other private source).
    assert summary["solar_share"] == pytest.approx(0.139, abs=0.001)
    assert summary["grid_share"] == pytest.approx(0.471, abs=0.001)
    total = by_sector[["solar_share", "grid_share", "unserved_share", "other_share"]].sum(axis=1)
    assert np.allclose(total, 1, atol=0.02)
    assert (by_sector["grid_share"] >= -1e-9).all()
