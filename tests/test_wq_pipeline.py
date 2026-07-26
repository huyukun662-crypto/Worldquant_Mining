import pytest

from mining_pipeline.wq_pipeline import setting_space
from mining_pipeline.expressions import expression_features, is_mineable


def test_china_space_uses_a_share_universe_and_supported_neutralizations():
    space = setting_space("chn")

    assert space["universe"] == ["TOP2000U"]
    assert "INDUSTRY" in space["neutralization"]
    assert "REVERSION_AND_MOMENTUM" in space["neutralization"]
    assert "COUNTRY" not in space["neutralization"]
    assert "STATISTICAL" not in space["neutralization"]


def test_region_spaces_are_independent_copies():
    first = setting_space("CHN")
    first["universe"].append("BAD")

    assert setting_space("CHN")["universe"] == ["TOP2000U"]


def test_unsupported_region_is_rejected():
    with pytest.raises(ValueError, match="unsupported region"):
        setting_space("EUR")


def test_structural_gate_rejects_trivial_random_draws():
    assert not is_mineable("scale(open)")
    assert not is_mineable("rank(divide(cap, cap))")
    assert not is_mineable("zscore(ts_mean(close, 20))")  # only one field


def test_structural_features_explain_candidate():
    expression = "rank(ts_corr(volume, returns, 20))"
    features = expression_features(expression)

    assert is_mineable(expression)
    assert features["fields"] == ["returns", "volume"]
    assert features["ts_operators"] == ["ts_corr"]
    assert features["has_window"] is True
