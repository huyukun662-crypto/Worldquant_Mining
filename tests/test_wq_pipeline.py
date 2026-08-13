import pytest

from mining_pipeline.wq_pipeline import A_SHARE_UNIVERSES, setting_space
from mining_pipeline.expressions import expression_features, is_mineable


def test_china_space_uses_a_share_universe_and_supported_neutralizations():
    space = setting_space("chn")

    assert space["universe"] == list(A_SHARE_UNIVERSES)
    assert "INDUSTRY" in space["neutralization"]
    assert "REVERSION_AND_MOMENTUM" in space["neutralization"]
    assert "COUNTRY" not in space["neutralization"]
    assert "STATISTICAL" not in space["neutralization"]


def test_region_spaces_are_independent_copies():
    first = setting_space("CHN")
    first["universe"].append("BAD")

    assert setting_space("CHN")["universe"] == list(A_SHARE_UNIVERSES)


def test_user_controls_universe_and_delay_scope():
    space = setting_space(
        "CHN", universe="CSI500", delay=0,
        neutralizations=["MARKET", "INDUSTRY"], decay=12,
    )

    assert space["universe"] == ["CSI500"]
    assert space["delay"] == [0]
    assert space["neutralization"] == ["MARKET", "INDUSTRY"]
    assert space["decay"] == [12]


def test_unsupported_region_is_rejected():
    with pytest.raises(ValueError, match="unsupported region"):
        setting_space("EUR")


def test_a_share_universe_catalog_has_requested_major_indices():
    assert A_SHARE_UNIVERSES == (
        "ALL_A", "SSE_COMPOSITE", "SSE50", "CSI_A500", "CSI300",
        "CSI500", "CSI800", "CSI1000", "CSI2000", "SZSE_COMPONENT",
        "SZSE100", "CHINEXT", "STAR50",
    )


@pytest.mark.parametrize(
    ("alias", "canonical"),
    [("上证指数", "SSE_COMPOSITE"), ("上证综指", "SSE_COMPOSITE"),
     ("深证成指", "SZSE_COMPONENT")],
)
def test_chinese_index_aliases(alias, canonical):
    assert setting_space("CHN", universe=alias)["universe"] == [canonical]


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
