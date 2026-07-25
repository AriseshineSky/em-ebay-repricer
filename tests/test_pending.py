# -*- coding: utf-8 -*-

from em_ebay_repricer.pending_store import (
    APPLY_STATUSES,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_SKIPPED_PRICE,
    build_pending_doc,
    build_tier_only_patch,
    iter_pending_docs,
    normalize_apply_statuses,
    pending_doc_id,
    pending_hit_to_product,
)


def _sample_prod(**overrides):
    prod = {
        "product_id": "100",
        "handle": "demo",
        "source_product_id": "123456789012",
        "catalog_price": 10.0,
        "variants": [
            {
                "variant_id": "200",
                "is_master": True,
                "price": 10.0,
                "currency": "USD",
            }
        ],
        "offer": {
            "price": 20.0,
            "quantity": 5,
            "currency": "USD",
            "src_price": 8.0,
        },
    }
    prod.update(overrides)
    return prod


def test_pending_doc_id():
    assert pending_doc_id("em-spree", "US", "100") == "em-spree_us_100"


def test_build_pending_doc_shape_and_tier_flags():
    existing = {"tier_cart": True, "tier_ads": False, "tier_catalog": False}
    doc = build_pending_doc(
        "em-spree",
        "us",
        _sample_prod(),
        status=STATUS_PENDING,
        tier="ads",
        plan_run_id="run1",
        existing=existing,
        source_doc={"date": "2026-07-21T18:00:00+00:00"},
        update_calc_at=True,
    )
    assert doc["_id"] == "em-spree_us_100"
    assert doc["status"] == STATUS_PENDING
    assert doc["tier"] == "ads"
    assert doc["tier_cart"] is True
    assert doc["tier_ads"] is True
    assert doc["tier_catalog"] is False
    assert doc["plan_run_id"] == "run1"
    assert doc["old_price"] == 10.0
    assert doc["offer"]["price"] == 20.0
    assert doc["calc_at"]
    assert doc["source_updated_at"]


def test_build_pending_doc_preserves_calc_at_when_not_updating():
    existing = {"calc_at": "2026-07-20T00:00:00+00:00", "tier_cart": True}
    doc = build_pending_doc(
        "em-spree",
        "us",
        _sample_prod(),
        status=STATUS_SKIPPED_PRICE,
        tier="cart",
        existing=existing,
        update_calc_at=False,
    )
    assert doc["calc_at"] == "2026-07-20T00:00:00+00:00"


def test_build_tier_only_patch():
    existing = {"tier_cart": True, "tier_ads": False, "tier_catalog": False}
    doc_id, body = build_tier_only_patch(existing, "ads", "em-spree", "us", "100")
    assert doc_id == "em-spree_us_100"
    assert body["doc"]["tier"] == "ads"
    assert body["doc"]["tier_ads"] is True
    assert body["doc"]["tier_cart"] is True


def test_pending_hit_to_product():
    hit = {
        "_id": "em-spree_us_100",
        "_source": {
            "product_id": "100",
            "handle": "demo",
            "ebay_id": "123456789012",
            "variants": [{"variant_id": "200", "is_master": True, "price": 10}],
            "offer": {"price": 20.0, "quantity": 5, "currency": "USD"},
        },
    }
    pid, prod = pending_hit_to_product(hit)
    assert pid == "100"
    assert prod["handle"] == "demo"
    assert prod["source_product_id"] == "123456789012"
    assert prod["offer"]["price"] == 20.0


def test_normalize_apply_statuses_defaults_to_pending_and_failed():
    assert normalize_apply_statuses(None) == list(APPLY_STATUSES)
    assert normalize_apply_statuses([]) == list(APPLY_STATUSES)
    assert normalize_apply_statuses("failed") == [STATUS_FAILED]
    assert normalize_apply_statuses(["pending", "failed", "pending"]) == [
        STATUS_PENDING,
        STATUS_FAILED,
    ]


def test_iter_pending_docs_queries_pending_and_failed_by_default():
    class FakeService:
        def __init__(self):
            self.query = None

        def scan(self, index, query=None, size=100):
            self.query = query
            return iter([])

    service = FakeService()
    list(iter_pending_docs(service, "em-spree", "us"))
    assert service.query["bool"]["filter"][0] == {
        "terms": {"status": [STATUS_PENDING, STATUS_FAILED]}
    }


def test_iter_pending_docs_single_status_uses_term():
    class FakeService:
        def __init__(self):
            self.query = None

        def scan(self, index, query=None, size=100):
            self.query = query
            return iter([])

    service = FakeService()
    list(iter_pending_docs(service, "em-spree", "us", status=STATUS_FAILED))
    assert service.query["bool"]["filter"][0] == {"term": {"status": STATUS_FAILED}}
