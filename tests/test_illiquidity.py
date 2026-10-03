"""Tests for the illiquidity-premium settings (IFRS 17 B79-B80)."""

import pytest

from ifrs17.illiquidity import (
    APPLICATION_RATIO,
    APPLICATION_RATIO_BY_LIQUIDITY,
    CREDIT_SHARE,
    CREDIT_SHARE_CDS,
    PORTFOLIO_LIQUIDITY,
    application_ratio,
    credit_share_from_cds,
    expected_loss_floor,
)


def test_chosen_policy_is_plain_hqm():
    assert CREDIT_SHARE == 0.0
    assert all(r == 1.0 for r in APPLICATION_RATIO.values())


def test_cds_alternative_matches_the_documented_procedure():
    # an A-heavy AAA-A mix reproduces the 55% option
    assert credit_share_from_cds({"AAA/AA": 0.2, "A": 0.8}) == pytest.approx(0.55)
    assert 0.51 <= CREDIT_SHARE_CDS <= 0.56
    with pytest.raises(ValueError):
        credit_share_from_cds({"A": 0.0})


def test_expected_loss_floor():
    # 0.08% annual default x 60% LGD over a 100 bp spread -> at least 4.8% of the spread is credit
    assert expected_loss_floor(0.0008, 0.60, 0.0100) == pytest.approx(0.048)
    assert expected_loss_floor(0.05, 1.0, 0.01) == 1.0
    with pytest.raises(ValueError):
        expected_loss_floor(0.001, 0.6, 0.0)


def test_graded_liquidity_option():
    vt, auto, va = (application_ratio(p, APPLICATION_RATIO_BY_LIQUIDITY) for p in ("VT", "AUTO", "VA"))
    assert vt > auto > va > 0
    assert application_ratio("RE_VT", APPLICATION_RATIO_BY_LIQUIDITY) == vt  # par. 63
    assert set(PORTFOLIO_LIQUIDITY.values()) <= set(APPLICATION_RATIO_BY_LIQUIDITY)
