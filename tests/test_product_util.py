# -*- coding: utf-8 -*-

from unittest.mock import MagicMock

import pytest

from em_ebay_repricer.spree.product_util import ProductUtil, SpreeSetOffersError


def _util():
    util = ProductUtil("https://spree.example.com", "tok", "v1")
    util.spree_api = MagicMock()
    util.spree_api.set_offers.return_value = {"succeed": True}
    return util


def _prod(offer=None):
    return {
        "handle": "demo",
        "source_product_id": "123",
        "variants": [{"variant_id": "200", "is_master": True}],
        "offer": offer
        or {
            "price": 29.991,
            "quantity": 50,
            "currency": "USD",
            "src_price": 12.345,
        },
    }


def test_build_coerces_string_numerics_to_json_numbers():
    util = _util()
    posted = util.set_products_offer(
        {
            "8338": _prod(
                {
                    "price": "29.991",
                    "quantity": "50",
                    "currency": "USD",
                    "src_price": "12.345",
                }
            )
        }
    )
    item = posted["8338"]["offers"]["200"]
    assert item["product_id"] == 8338
    assert item["variant_id"] == 200
    assert isinstance(item["product_id"], int)
    assert isinstance(item["variant_id"], int)
    assert item["price"] == 29.99
    assert item["quantity"] == 50
    assert item["cost_price"] == 12.35
    assert isinstance(item["price"], float)
    assert isinstance(item["quantity"], int)
    assert isinstance(item["cost_price"], float)


def test_set_offers_500_raises_so_apply_can_mark_failed():
    util = _util()
    util.spree_api.set_offers.return_value = {
        "status": 500,
        "error": "Internal Server Error",
    }
    with pytest.raises(SpreeSetOffersError) as exc_info:
        util.set_products_offer({"100": _prod()})
    assert exc_info.value.status == 500
    assert exc_info.value.is_5xx is True


def test_set_offers_503_is_5xx():
    util = _util()
    util.spree_api.set_offers.return_value = {"status": 503, "error": "Unavailable"}
    with pytest.raises(SpreeSetOffersError) as exc_info:
        util.set_products_offer({"100": _prod()})
    assert exc_info.value.is_5xx is True


def test_set_offers_400_is_not_5xx():
    util = _util()
    util.spree_api.set_offers.return_value = {"status": 400, "error": "Bad Request"}
    with pytest.raises(SpreeSetOffersError) as exc_info:
        util.set_products_offer({"100": _prod()})
    assert exc_info.value.status == 400
    assert exc_info.value.is_5xx is False
