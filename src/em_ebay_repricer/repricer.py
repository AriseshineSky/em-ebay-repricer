# -*- coding: utf-8 -*-

from __future__ import annotations

import datetime
import time

import dateparser

from runtime import logger
from em_ebay_repricer.ebay_products_filter import EbayProductsFilterPipeline


class EbayRepricer:
    """Calculate Ebay offers and optionally write Spree set_offers."""

    def __init__(
        self,
        product_service,
        price_calculator,
        product_util,
        marketplace="us",
        ttl=30,
        dry_run=False,
        batch_size=250,
    ):
        self.product_service = product_service
        self.price_calc = price_calculator
        self.product_util = product_util
        self.marketplace = marketplace.lower()
        self.indice_name = "ebay_{}_products".format(self.marketplace)
        self.ttl = ttl
        self.dry_run = dry_run
        self.batch_size = batch_size
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
            "skipped_incomplete": 0,
        }

    def process_batch(self, products_by_ebay_id):
        """products_by_ebay_id: source_product_id -> enriched store product dict."""
        if not products_by_ebay_id:
            return
        ebay_ids = list(products_by_ebay_id.keys())
        es_docs = self._fetch_es(ebay_ids)
        to_update = {}

        for ebay_id, prod in products_by_ebay_id.items():
            self.stats["products_cnt"] += 1
            if not prod.get("product_id") or not prod.get("handle") or not prod.get("variants"):
                self.stats["skipped_incomplete"] += 1
                continue

            es_doc = es_docs.get(ebay_id) or es_docs.get(str(ebay_id))
            offer = self._calc_offer(ebay_id, es_doc)
            prod["offer"] = offer
            to_update[prod["product_id"]] = prod

        if not to_update:
            return

        if self.dry_run:
            self.stats["updated_cnt"] += len(to_update)
            return

        try:
            self.product_util.set_products_offer(to_update, None)
            self.stats["updated_cnt"] += len(to_update)
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
        currency = "USD"
        if not product:
            self.stats["missing_es"] += 1
            self.stats["out_of_stock"] += 1
            return {"price": 0, "quantity": 0, "currency": currency}

        src_product_price = product.get("price", 0) or 0
        src_shipping_fee = product.get("shipping_fee", 0) or 0
        currency = product.get("currency", None) or "USD"
        result = self.ebay_filter.check_product(product)
        if not src_product_price or not result.get("passed", False):
            if not result.get("passed", False):
                reason = result.get("reason", "Unknown")
                self.stats["filtered"].setdefault(reason, 0)
                self.stats["filtered"][reason] += 1
            self.stats["out_of_stock"] += 1
            return {"price": 0, "quantity": 0, "currency": currency}

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
            return {"price": 0, "quantity": 0, "currency": currency}
        if update_date < self.expire_date:
            self.stats["expired_cnt"] += 1

        src_offer = {
            "price": float(src_product_price) + float(src_shipping_fee),
            "currency": currency,
        }
        offer = self.price_calc.calc_offer(src_offer)
        if not offer:
            self.stats["out_of_stock"] += 1
            return {"price": 0, "quantity": 0, "currency": currency}

        if float(offer.get("quantity", 0) or 0) > 0:
            self.stats["in_stock"] += 1
        else:
            self.stats["out_of_stock"] += 1
        return offer
