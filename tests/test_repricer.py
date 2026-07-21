# -*- coding: utf-8 -*-

from unittest.mock import MagicMock, patch

from em_ebay_repricer.pending_store import STATUS_PENDING, STATUS_SKIPPED_PRICE
from em_ebay_repricer.repricer import EbayRepricer


def _store_prod(product_id="100", price=10.0):
    return {
        "product_id": product_id,
        "handle": "demo-{}".format(product_id),
        "source_product_id": "ebay-{}".format(product_id),
        "catalog_price": price,
        "variants": [
            {
                "variant_id": str(int(product_id) + 100),
                "is_master": True,
                "price": price,
                "currency": "USD",
            }
        ],
    }


def _make_repricer(**kwargs):
    defaults = dict(
        product_service=MagicMock(),
        price_calculator=MagicMock(),
        product_util=MagicMock(),
        marketplace="us",
        store_code="em-spree",
        mode=EbayRepricer.MODE_PLAN,
        dry_run=False,
        force=False,
        price_diff_threshold=1.0,
        plan_run_id="test-run",
    )
    defaults.update(kwargs)
    return EbayRepricer(**defaults)


@patch("em_ebay_repricer.repricer.save_pending_docs")
@patch("em_ebay_repricer.repricer.mget_pending", return_value={})
def test_plan_mode_writes_pending_and_skips_spree(mock_mget, mock_save):
    repricer = _make_repricer()
    offer = {"price": 25.0, "quantity": 3, "currency": "USD", "src_price": 8.0}
    with patch.object(repricer, "_fetch_es", return_value={"ebay-100": {"date": "2026-07-21"}}):
        with patch.object(repricer, "_calc_offer", return_value=(offer, None)):
            repricer.active_tier = "cart"
            repricer.process_batch({"ebay-100": _store_prod()}, tier="cart")

    assert repricer.stats["planned_cnt"] == 1
    assert repricer.stats["updated_cnt"] == 0
    mock_save.assert_called_once()
    docs = mock_save.call_args[0][1]
    assert docs[0]["status"] == STATUS_PENDING
    assert docs[0]["tier_cart"] is True
    repricer.product_util.set_products_offer.assert_not_called()


@patch("em_ebay_repricer.repricer.save_pending_docs")
@patch("em_ebay_repricer.repricer.mget_pending", return_value={})
def test_plan_skips_price_within_threshold(mock_mget, mock_save):
    repricer = _make_repricer(price_diff_threshold=1.0)
    offer = {"price": 10.4, "quantity": 3, "currency": "USD", "src_price": 8.0}
    with patch.object(repricer, "_fetch_es", return_value={"ebay-100": {"date": "2026-07-21"}}):
        with patch.object(repricer, "_calc_offer", return_value=(offer, None)):
            repricer.process_batch({"ebay-100": _store_prod(price=10.0)}, tier="ads")

    assert repricer.stats["skipped_price"] == 1
    assert repricer.stats["planned_cnt"] == 0
    docs = mock_save.call_args[0][1]
    assert docs[0]["status"] == STATUS_SKIPPED_PRICE
    assert docs[0]["tier_ads"] is True


@patch("em_ebay_repricer.repricer.apply_tier_patches")
@patch("em_ebay_repricer.repricer.save_pending_docs")
def test_plan_skips_fresh_and_patches_tier_only(mock_save, mock_patch):
    pending_id = "em-spree_us_100"
    existing = {
        "calc_at": "2026-07-21T18:00:00+00:00",
        "tier_cart": True,
        "tier_ads": False,
        "tier_catalog": False,
    }
    with patch(
        "em_ebay_repricer.repricer.mget_pending",
        return_value={pending_id: existing},
    ):
        repricer = _make_repricer()
        # Source older than calc_at → skip recalc
        with patch.object(
            repricer,
            "_fetch_es",
            return_value={"ebay-100": {"date": "2026-07-21T17:00:00+00:00"}},
        ):
            with patch.object(repricer, "_calc_offer") as mock_calc:
                repricer.process_batch({"ebay-100": _store_prod()}, tier="ads")
                mock_calc.assert_not_called()

    assert repricer.stats["skipped_fresh"] == 1
    assert repricer.stats["planned_cnt"] == 0
    mock_save.assert_not_called()
    mock_patch.assert_called_once()
    patches = mock_patch.call_args[0][1]
    assert patches[0][0] == pending_id
    assert patches[0][1]["doc"]["tier_ads"] is True


@patch("em_ebay_repricer.repricer.save_pending_docs")
@patch("em_ebay_repricer.repricer.mget_pending", return_value={})
def test_live_mode_calls_spree_for_pending(mock_mget, mock_save):
    util = MagicMock()
    repricer = _make_repricer(mode=EbayRepricer.MODE_LIVE, product_util=util)
    offer = {"price": 25.0, "quantity": 3, "currency": "USD", "src_price": 8.0}
    with patch.object(repricer, "_fetch_es", return_value={"ebay-100": {"date": "2026-07-21"}}):
        with patch.object(repricer, "_calc_offer", return_value=(offer, None)):
            repricer.process_batch({"ebay-100": _store_prod()}, tier="cart")

    assert repricer.stats["planned_cnt"] == 1
    assert repricer.stats["updated_cnt"] == 1
    util.set_products_offer.assert_called_once()
