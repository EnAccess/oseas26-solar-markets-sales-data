"""Unit tests for the shared market-gap calculation (services/market_gap.py)."""
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from app.services import market_gap as mg

SETTINGS = SimpleNamespace(need_w_population=0.4, need_w_grid_distance=0.4, need_w_darkness=0.2)


def frame(**cols):
    n = len(next(iter(cols.values())))
    base = {
        "cell_id": [f"RW_{i:04d}" for i in range(n)],
        "population_density": np.linspace(10, 1000, n),
        "distance_to_grid_km": np.linspace(0, 30, n),
        "nighttime_radiance": np.linspace(5, 0.1, n),
        "survey_solar_share": np.full(n, 0.2),
        "survey_solar_hh_sampled": np.full(n, 20),
    }
    base.update(cols)
    return pd.DataFrame(base)


def test_scores_are_bounded_and_deterministic():
    cells = frame(population_density=np.linspace(0, 5000, 50))
    a = mg.add_market_scores(cells, SETTINGS)
    b = mg.add_market_scores(cells, SETTINGS)
    assert a["market_gap_score"].between(0, 1).all()
    assert a["energy_need_score"].between(0, 1).all()
    pd.testing.assert_frame_equal(a, b)


def test_formula_is_need_times_one_minus_uptake():
    out = mg.add_market_scores(frame(survey_solar_share=np.linspace(0, 0.5, 20)), SETTINGS)
    expected = (out["energy_need_score"] * (1 - out["solar_uptake"])).round(4)
    assert np.allclose(out["market_gap_score"], expected, atol=1e-4)


def test_missing_uptake_is_not_treated_as_zero_ownership():
    cells = frame(survey_solar_share=[np.nan] + [0.2] * 9)
    out = mg.add_market_scores(cells, SETTINGS)
    assert pd.isna(out.loc[0, "market_gap_score"])
    assert out.loc[0, "uptake_source"] == mg.UPTAKE_UNKNOWN
    assert out.loc[0, "evidence_level"] == "insufficient"
    assert "Solar uptake evidence" in out.loc[0, "missing_inputs"]
    assert out.loc[1:, "market_gap_score"].notna().all()


def test_missing_need_input_gives_no_score():
    cells = frame(nighttime_radiance=[np.nan] + list(np.linspace(1, 2, 9)))
    out = mg.add_market_scores(cells, SETTINGS)
    assert pd.isna(out.loc[0, "energy_need_score"]) and pd.isna(out.loc[0, "market_gap_score"])
    assert "Nighttime radiance" in out.loc[0, "missing_inputs"]


def test_zero_values_are_valid_observations():
    cells = frame(population_density=[0.0] * 5 + [500.0] * 5, distance_to_grid_km=[0.0] * 10)
    out = mg.add_market_scores(cells, SETTINGS)
    assert out["market_gap_score"].notna().all()
    assert out.loc[0, "energy_need_score"] < out.loc[9, "energy_need_score"]


def test_higher_survey_ownership_lowers_score_all_else_equal():
    cells = frame(population_density=[500.0] * 2, distance_to_grid_km=[10.0] * 2,
                  nighttime_radiance=[0.2] * 2, survey_solar_share=[0.05, 0.40])
    out = mg.add_market_scores(cells, SETTINGS)
    assert out.loc[0, "market_gap_score"] > out.loc[1, "market_gap_score"]


def test_darkness_alone_cannot_create_a_score_without_uptake_evidence():
    cells = frame(nighttime_radiance=[0.01] * 4, survey_solar_share=[np.nan] * 4)
    assert mg.add_market_scores(cells, SETTINGS)["market_gap_score"].isna().all()


def test_model_prediction_used_only_when_trusted():
    cells = frame(predicted_solar_penetration=[0.9] * 10)
    untrusted = mg.add_market_scores(cells, SETTINGS, model_trusted=False)
    trusted = mg.add_market_scores(cells, SETTINGS, model_trusted=True)
    assert (untrusted["uptake_source"] == mg.UPTAKE_SURVEY).all()
    assert (trusted["uptake_source"] == mg.UPTAKE_MODEL).all()
    assert (trusted["market_gap_score"] <= untrusted["market_gap_score"]).all()


def test_small_survey_sample_is_flagged_limited():
    out = mg.add_market_scores(frame(survey_solar_hh_sampled=[3] * 5 + [30] * 5), SETTINGS)
    assert (out.loc[:4, "evidence_level"] == "limited").all()
    assert (out.loc[5:, "evidence_level"] == "indicative").all()


def test_scale_handles_constant_and_missing_columns():
    s = mg.scale(pd.Series([2.0, 2.0, np.nan]))
    assert s.iloc[0] == 0.0 and pd.isna(s.iloc[2])
    assert mg.scale(pd.Series([np.nan, np.nan])).isna().all()
    out = mg.add_market_scores(frame(population_density=np.linspace(1, 9, 5)).drop(columns=["nighttime_radiance"]), SETTINGS)
    assert out["market_gap_score"].isna().all()


@pytest.mark.parametrize("value,expected", [(None, None), (np.nan, None), (0.0, 0), (0.523, 52), (1.0, 100)])
def test_opportunity_score_display(value, expected):
    assert mg.opportunity_score_100(value) == expected
