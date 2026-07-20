# -*- coding: utf-8 -*-

from __future__ import annotations

import csv
import datetime
import logging
import os
import time

import dateparser

from .catalog_pg import CatalogEbayProductsSource
from .ebay_products_filter import EbayProductsFilterPipeline

logger = logging.getLogger("ebay_reprice_export")

CSV_FIELDS = [
  "product_id",
  "source_product_id",
  "handle",
  "variant_id",
  "catalog_price",
  "catalog_availability",
  "ebay_price",
  "ebay_shipping_fee",
  "ebay_available_qty",
  "ebay_existence",
  "ebay_date",
  "calculated_price",
  "calculated_quantity",
  "calculated_availability",
  "filter_passed",
  "filter_reason",
  "expired",
]


class EbayRepricerExporter:
  def __init__(
    self,
    product_service,
    price_calculator,
    marketplace,
    ttl=30,
    output_path=None,
    pg_config=None,
    limit=0,
    batch_size=250,
  ):
    self.product_service = product_service
    self.price_calc = price_calculator
    self.marketplace = marketplace.lower()
    self.indice_name = "ebay_{}_products".format(self.marketplace)
    self.ttl = ttl
    self.output_path = output_path
    self.pg_config = pg_config
    self.limit = int(limit or 0)
    self.batch_size = int(batch_size or 250)
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
      "exported_cnt": 0,
    }
    self._csv_fh = None
    self._csv_writer = None
    self._t0 = None

  def run(self):
    if not self.output_path:
      raise ValueError("output_path is required")

    output_path = os.path.abspath(os.path.expanduser(self.output_path))
    out_dir = os.path.dirname(output_path)
    if out_dir:
      os.makedirs(out_dir, exist_ok=True)

    catalog_source = CatalogEbayProductsSource(self.pg_config)
    products = {}
    self._t0 = time.time()

    self._csv_fh = open(output_path, "w", newline="", encoding="utf-8")
    try:
      self._csv_writer = csv.DictWriter(self._csv_fh, fieldnames=CSV_FIELDS)
      self._csv_writer.writeheader()

      for ebay_prod in catalog_source.iter_products(self.marketplace, limit=self.limit):
        self.stats["products_cnt"] += 1
        products[ebay_prod["source_product_id"]] = ebay_prod

        if len(products) < self.batch_size:
          continue

        self.process_products(products)
        products.clear()
        self._maybe_log_progress()

      if products:
        self.process_products(products)
        products.clear()
        self._maybe_log_progress(force=True)
    finally:
      if self._csv_fh is not None:
        self._csv_fh.close()
        self._csv_fh = None
        self._csv_writer = None

    elapsed = time.time() - self._t0
    logger.info(
      "[EbayRepricerExport] path=%s products=%s exported=%s in_stock=%s "
      "out_of_stock=%s expired=%s missing_es=%s filtered=%s elapsed=%.1fs rate=%.0f/s",
      output_path,
      self.stats["products_cnt"],
      self.stats["exported_cnt"],
      self.stats["in_stock"],
      self.stats["out_of_stock"],
      self.stats["expired_cnt"],
      self.stats["missing_es"],
      self.stats["filtered"],
      elapsed,
      (self.stats["exported_cnt"] / elapsed) if elapsed > 0 else 0,
    )
    return self.stats

  def get_stats(self):
    return self.stats

  def _maybe_log_progress(self, force=False):
    n = self.stats["exported_cnt"]
    if not force and n % 5000 != 0:
      return
    elapsed = time.time() - self._t0
    rate = n / elapsed if elapsed > 0 else 0
    logger.info(
      "[Progress] exported=%s elapsed=%.1fs rate=%.0f/s in_stock=%s out_of_stock=%s",
      n, elapsed, rate, self.stats["in_stock"], self.stats["out_of_stock"],
    )

  def process_products(self, prods):
    product_ids = list(prods.keys())
    products = None
    max_retries = 3
    while max_retries > 0:
      try:
        products = self.product_service.search_products(self.indice_name, product_ids)
        if not isinstance(products, dict):
          logger.info("[ProductService] Temporary unavailable! retry...")
          max_retries -= 1
          time.sleep(5)
          continue
        break
      except Exception as e:
        logger.exception(e)
        max_retries -= 1
        time.sleep(3)

    if not products:
      products = {}

    for source_product_id, prod in prods.items():
      product = products.get(source_product_id) or products.get(str(source_product_id))
      row = self._build_row(prod, product)
      self._write_row(row)

  def _build_row(self, prod, product):
    catalog_price = prod.get("catalog_price")
    catalog_availability = prod.get("catalog_availability") or ""
    variant_id = prod.get("variant_id") or ""
    if not variant_id and prod.get("variants"):
      variant_id = prod["variants"][0].get("variant_id", "")

    row = {
      "product_id": prod.get("product_id", ""),
      "source_product_id": prod.get("source_product_id", ""),
      "handle": prod.get("handle", ""),
      "variant_id": variant_id,
      "catalog_price": catalog_price if catalog_price is not None else "",
      "catalog_availability": catalog_availability,
      "ebay_price": "",
      "ebay_shipping_fee": "",
      "ebay_available_qty": "",
      "ebay_existence": "",
      "ebay_date": "",
      "calculated_price": 0,
      "calculated_quantity": 0,
      "calculated_availability": "out of stock",
      "filter_passed": False,
      "filter_reason": "",
      "expired": False,
    }

    if not product:
      self.stats["missing_es"] += 1
      self.stats["out_of_stock"] += 1
      row["filter_reason"] = "MissingES"
      return row

    src_product_price = product.get("price", 0) or 0
    src_shipping_fee = product.get("shipping_fee", 0) or 0
    currency = product.get("currency", None) or "USD"
    available_qty = product.get("available_qty", None)
    existence = product.get("existence", None)
    update_date_s = product.get("date", product.get("time", None))

    row["ebay_price"] = src_product_price
    row["ebay_shipping_fee"] = src_shipping_fee
    row["ebay_available_qty"] = "" if available_qty is None else available_qty
    row["ebay_existence"] = "" if existence is None else existence
    row["ebay_date"] = update_date_s or ""

    result = self.ebay_filter.check_product(product)
    passed = bool(result.get("passed", False))
    row["filter_passed"] = passed
    if not passed:
      reason = result.get("reason", "Unknown")
      row["filter_reason"] = reason
      self.stats["filtered"].setdefault(reason, 0)
      self.stats["filtered"][reason] += 1
      self.stats["out_of_stock"] += 1
      return row

    if not src_product_price:
      self.stats["out_of_stock"] += 1
      row["filter_reason"] = "NoPrice"
      return row

    update_date = None
    if update_date_s:
      try:
        update_date = dateparser.parse(update_date_s).date()
      except Exception:
        update_date = None

    if not update_date:
      row["expired"] = True
      self.stats["expired_cnt"] += 1
      self.stats["out_of_stock"] += 1
      row["filter_reason"] = "ExpiredNoDate"
      return row

    expired = update_date < self.expire_date
    row["expired"] = expired
    if expired:
      self.stats["expired_cnt"] += 1

    src_offer = {
      "price": float(src_product_price) + float(src_shipping_fee),
      "currency": currency,
    }
    offer = self.price_calc.calc_offer(src_offer)
    if not offer:
      self.stats["out_of_stock"] += 1
      row["filter_reason"] = "CalcFailed"
      return row

    calc_price = round(float(offer.get("price", 0) or 0), 2)
    calc_qty = int(float(offer.get("quantity", 0) or 0))
    row["calculated_price"] = calc_price
    row["calculated_quantity"] = calc_qty
    if calc_qty > 0:
      row["calculated_availability"] = "in stock"
      self.stats["in_stock"] += 1
    else:
      row["calculated_availability"] = "out of stock"
      self.stats["out_of_stock"] += 1

    return row

  def _write_row(self, row):
    if not self._csv_writer:
      return
    self._csv_writer.writerow(row)
    self.stats["exported_cnt"] += 1
