# -*- coding: utf-8 -*-

import pytest

from em_ebay_repricer.frequency import (
    DEFAULT_PRICE_DIFF_THRESHOLD,
    current_catalog_price,
    needs_recalc,
    resolve_price_diff_threshold,
    should_skip_by_price_diff,
    tier_flag_field,
)


def test_should_skip_by_price_diff():
    assert should_skip_by_price_diff(10.0, 10.5, threshold=1.0) is True
    assert should_skip_by_price_diff(10.0, 12.0, threshold=1.0) is False
    assert should_skip_by_price_diff(10.0, 10.5, force=True) is False
    assert should_skip_by_price_diff(None, 10.0) is False


def test_resolve_price_diff_threshold_default_config_and_override():
    assert resolve_price_diff_threshold() == DEFAULT_PRICE_DIFF_THRESHOLD
    assert (
        resolve_price_diff_threshold({"ebay_repricer": {"price_diff_threshold": "0.5"}})
        == 0.5
    )
    assert (
        resolve_price_diff_threshold(
            {"ebay_repricer": {"price_diff_threshold": "2"}}, override=0.25
        )
        == 0.25
    )
    with pytest.raises(ValueError):
        resolve_price_diff_threshold({"ebay_repricer": {"price_diff_threshold": "-1"}})


def test_current_catalog_price_prefers_catalog_then_master():
    assert current_catalog_price({"catalog_price": "12.5"}) == 12.5
    assert (
        current_catalog_price(
            {
                "variants": [
                    {"is_master": False, "price": 9},
                    {"is_master": True, "price": 11},
                ]
            }
        )
        == 11.0
    )


def test_needs_recalc_by_source_vs_calc_at():
    calc_at = "2026-07-21T12:00:00+00:00"
    older = {"date": "2026-07-21T11:00:00+00:00"}
    newer = {"date": "2026-07-21T13:00:00+00:00"}
    pending = {"calc_at": calc_at}

    assert needs_recalc(newer, pending) is True
    assert needs_recalc(older, pending) is False
    assert needs_recalc(older, pending, force=True) is True
    assert needs_recalc(newer, None) is True
    assert needs_recalc(None, pending) is True


def test_tier_flag_field():
    assert tier_flag_field("Cart") == "tier_cart"
