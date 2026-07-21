# -*- coding: utf-8 -*-

import datetime
from unittest.mock import MagicMock

import pytest

from em_ebay_repricer.metrics import (
    METRICS_INDEX,
    run_kind_for_tiers,
    save_repricer_metrics,
)
from em_ebay_repricer.sources.tiers import ALL_TIERS, resolve_tiers


def _sample_stats(**overrides):
    stats = {
        "products_cnt": 10,
        "updated_cnt": 4,
        "planned_cnt": 3,
        "skipped_price": 2,
        "skipped_fresh": 1,
        "skipped_incomplete": 0,
        "skipped_discontinued": 0,
        "expired_cnt": 0,
        "in_stock": 8,
        "out_of_stock": 1,
        "missing_es": 0,
        "filtered": {"NotAvailable": 1},
    }
    stats.update(overrides)
    return stats


def test_resolve_tiers_default_and_order():
    assert resolve_tiers(()) == list(ALL_TIERS)
    assert resolve_tiers(("ads,cart",)) == ["cart", "ads"]
    assert resolve_tiers(("catalog",)) == ["catalog"]


def test_resolve_tiers_unknown():
    with pytest.raises(ValueError):
        resolve_tiers(("nope",))


def test_run_kind_for_tiers():
    assert run_kind_for_tiers(["cart"]) == "cart"
    assert run_kind_for_tiers(["ads"]) == "ads"
    assert run_kind_for_tiers(["catalog"]) == "catalog"
    assert run_kind_for_tiers(["cart", "ads", "catalog"]) == "all"
    assert run_kind_for_tiers(["ads", "cart"]) == "cart,ads"
    assert run_kind_for_tiers(["all"]) == "unknown"
    assert run_kind_for_tiers([]) == "unknown"


def test_save_repricer_metrics_plan_run():
    service = MagicMock()
    start = datetime.datetime(2026, 7, 21, 18, 0, 0)
    end = datetime.datetime(2026, 7, 21, 18, 0, 5)
    save_repricer_metrics(
        product_service=service,
        store_code="em-spree",
        marketplace="us",
        stats=_sample_stats(),
        start_time=start,
        end_time=end,
        plan=True,
        plan_run_id="abc123",
        price_diff_threshold=1.0,
        tiers=["ads"],
        tier_stats={"ads": {"seed_cnt": 100, "planned_cnt": 3}},
    )
    service.ensure_index.assert_called_once_with(METRICS_INDEX)
    index, docs = service.save_products.call_args[0]
    assert index == METRICS_INDEX
    doc = docs[0]
    assert doc["source"] == "ebay_repricer_plan"
    assert doc["metric_kind"] == "plan"
    assert doc["run_kind"] == "ads"
    assert doc["tiers"] == ["ads"]
    assert doc["planned_cnt"] == 3
    assert doc["skipped_fresh"] == 1
    assert doc["skipped_price"] == 2
    assert doc["plan_run_id"] == "abc123"
    assert doc["_id"].startswith("ebay_repricer_plan_us_ads_")


def test_save_repricer_metrics_apply_all_tiers_is_run_kind_all():
    service = MagicMock()
    start = datetime.datetime(2026, 7, 21, 18, 0, 0)
    end = datetime.datetime(2026, 7, 21, 18, 0, 1)
    save_repricer_metrics(
        product_service=service,
        store_code="em-spree",
        marketplace="us",
        stats=_sample_stats(planned_cnt=0, updated_cnt=53),
        start_time=start,
        end_time=end,
        plan=False,
        tiers=["cart", "ads", "catalog"],
    )
    doc = service.save_products.call_args[0][1][0]
    assert doc["source"] == "ebay_repricer"
    assert doc["metric_kind"] == "final"
    assert doc["run_kind"] == "all"
    assert doc["updated_cnt"] == 53
