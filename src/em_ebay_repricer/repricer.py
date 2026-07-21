# -*- coding: utf-8 -*-

from __future__ import annotations

import datetime
import time
import uuid

import dateparser

from em_ebay_repricer.ebay_products_filter import EbayProductsFilterPipeline
from em_ebay_repricer.frequency import (
    DEFAULT_PRICE_DIFF_THRESHOLD,
    current_catalog_price,
    needs_recalc,
    should_skip_by_price_diff,
)
from em_ebay_repricer.pending_store import (
    STATUS_FILTERED,
    STATUS_PENDING,
    STATUS_SKIPPED_PRICE,
    apply_tier_patches,
    build_pending_doc,
    build_tier_only_patch,
    mget_pending,
    pending_doc_id,
    save_pending_docs,
)
from em_ebay_repricer.runtime import logger


class EbayRepricer:
    """Calculate Ebay offers; plan to ES pending and/or write Spree set_offers."""

    MODE_LIVE = "live"
    MODE_PLAN = "plan"

    def __init__(
        self,
        product_service,
        price_calculator,
        product_util,
        marketplace="us",
        store_code="em-spree",
        ttl=30,
        dry_run=False,
        batch_size=250,
        mode=MODE_LIVE,
        force=False,
        price_diff_threshold=DEFAULT_PRICE_DIFF_THRESHOLD,
        plan_run_id=None,
    ):
        self.product_service = product_service
        self.price_calc = price_calculator
        self.product_util = product_util
        self.marketplace = marketplace.lower()
        self.store_code = store_code
        self.indice_name = "ebay_{}_products".format(self.marketplace)
        self.ttl = ttl
        self.dry_run = dry_run
        self.batch_size = batch_size
        self.mode = mode
        self.force = bool(force)
        self.price_diff_threshold = float(price_diff_threshold)
        self.plan_run_id = plan_run_id or uuid.uuid4().hex
        self.active_tier = None
        today = datetime.date.today()
        self.expire_date = today - datetime.timedelta(days=ttl)
        self.ebay_filter = EbayProductsFilterPipeline(20, 95)
        self.stats = {
            "products_cnt": 0,
            "expired_cnt": 0,
            "filtered": {},
            "in_stock": 0,
            "out_of_stock": 0,
            "missing_es": 0,
            "updated_cnt": 0,
            "planned_cnt": 0,
            "skipped_incomplete": 0,
            "skipped_discontinued": 0,
            "skipped_price": 0,
            "skipped_fresh": 0,
        }

    def process_batch(self, products_by_ebay_id, tier=None):
        """products_by_ebay_id: source_product_id -> enriched store product dict."""
        if not products_by_ebay_id:
            return
        tier = tier or self.active_tier
        ebay_ids = list(products_by_ebay_id.keys())
        es_docs = self._fetch_es(ebay_ids)

        product_ids = [
            str(p.get("product_id"))
            for p in products_by_ebay_id.values()
            if p.get("product_id")
        ]
        pending_by_id = {}
        try:
            raw_pending = mget_pending(
                self.product_service, self.store_code, self.marketplace, product_ids
            )
            for pid in product_ids:
                doc_id = pending_doc_id(self.store_code, self.marketplace, pid)
                if doc_id in raw_pending:
                    pending_by_id[pid] = raw_pending[doc_id]
        except Exception as e:
            logger.exception(e)

        pending_docs = []
        tier_patches = []
        to_spree = {}

        for ebay_id, prod in products_by_ebay_id.items():
            self.stats["products_cnt"] += 1
            if prod.get("discontinued"):
                self.stats["skipped_discontinued"] += 1
                self.stats["filtered"].setdefault("Discontinued", 0)
                self.stats["filtered"]["Discontinued"] += 1
                continue
            if not prod.get("product_id") or not prod.get("handle") or not prod.get("variants"):
                self.stats["skipped_incomplete"] += 1
                continue

            product_id = str(prod["product_id"])
            existing = pending_by_id.get(product_id)
            es_doc = es_docs.get(ebay_id) or es_docs.get(str(ebay_id))

            if not needs_recalc(es_doc, existing, force=self.force):
                self.stats["skipped_fresh"] += 1
                doc_id, patch = build_tier_only_patch(
                    existing, tier, self.store_code, self.marketplace, product_id
                )
                if doc_id and patch:
                    tier_patches.append((doc_id, patch))
                continue

            offer, filter_reason = self._calc_offer(ebay_id, es_doc)
            prod["offer"] = offer

            if filter_reason:
                status = STATUS_FILTERED
            else:
                old_price = current_catalog_price(prod)
                new_price = offer.get("price") if isinstance(offer, dict) else None
                if should_skip_by_price_diff(
                    old_price,
                    new_price,
                    threshold=self.price_diff_threshold,
                    force=self.force,
                ):
                    status = STATUS_SKIPPED_PRICE
                    self.stats["skipped_price"] += 1
                else:
                    status = STATUS_PENDING
                    self.stats["planned_cnt"] += 1

            doc = build_pending_doc(
                self.store_code,
                self.marketplace,
                prod,
                status=status,
                tier=tier,
                plan_run_id=self.plan_run_id,
                existing=existing,
                source_doc=es_doc,
                update_calc_at=True,
            )
            if doc:
                pending_docs.append(doc)

            if status == STATUS_PENDING and self.mode == self.MODE_LIVE:
                to_spree[product_id] = prod

        if not self.dry_run:
            if pending_docs:
                save_pending_docs(self.product_service, pending_docs)
            if tier_patches:
                apply_tier_patches(self.product_service, tier_patches)

        if self.mode == self.MODE_PLAN:
            return

        if not to_spree:
            return

        if self.dry_run:
            self.stats["updated_cnt"] += len(to_spree)
            return

        try:
            self.product_util.set_products_offer(to_spree, None)
            self.stats["updated_cnt"] += len(to_spree)
        except Exception as e:
            logger.exception(e)

    def _fetch_es(self, ebay_ids):
        max_retries = 3
        while max_retries > 0:
            try:
                products = self.product_service.search_products(
                    self.indice_name, ebay_ids
                )
                if isinstance(products, dict):
                    return products
                logger.info("[ProductService] Temporary unavailable! retry...")
            except Exception as e:
                logger.exception(e)
            max_retries -= 1
            time.sleep(3)
        return {}

    def _calc_offer(self, ebay_id, product):
        """Return (offer_dict, filter_reason_or_None)."""
        currency = "USD"
        if not product:
            self.stats["missing_es"] += 1
            self.stats["out_of_stock"] += 1
            return {"price": 0, "quantity": 0, "currency": currency}, "MissingES"

        src_product_price = product.get("price", 0) or 0
        src_shipping_fee = product.get("shipping_fee", 0) or 0
        currency = product.get("currency", None) or "USD"
        result = self.ebay_filter.check_product(product)
        if not src_product_price or not result.get("passed", False):
            reason = (
                result.get("reason", "Unknown")
                if not result.get("passed")
                else "NoPrice"
            )
            if not result.get("passed", False):
                self.stats["filtered"].setdefault(reason, 0)
                self.stats["filtered"][reason] += 1
            self.stats["out_of_stock"] += 1
            return {"price": 0, "quantity": 0, "currency": currency}, reason

        update_date_s = product.get("date", product.get("time", None))
        update_date = None
        if update_date_s:
            try:
                update_date = dateparser.parse(update_date_s).date()
            except Exception:
                update_date = None
        if not update_date:
            self.stats["expired_cnt"] += 1
            self.stats["out_of_stock"] += 1
            return {"price": 0, "quantity": 0, "currency": currency}, "NoDate"
        if update_date < self.expire_date:
            self.stats["expired_cnt"] += 1

        src_offer = {
            "price": float(src_product_price) + float(src_shipping_fee),
            "currency": currency,
        }
        offer = self.price_calc.calc_offer(src_offer)
        if not offer:
            self.stats["out_of_stock"] += 1
            return {"price": 0, "quantity": 0, "currency": currency}, "CalcFailed"

        if float(offer.get("quantity", 0) or 0) > 0:
            self.stats["in_stock"] += 1
        else:
            self.stats["out_of_stock"] += 1
        return offer, None
