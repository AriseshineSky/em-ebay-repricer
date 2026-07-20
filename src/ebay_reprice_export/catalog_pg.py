# -*- coding: utf-8 -*-
"""Stream Ebay products from em-catalog product_sources + product_catalogs."""

from __future__ import annotations

import os
import re

import psycopg2

_TABLE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def build_pg_dsn(pg_config):
  env_url = (
    os.getenv("CATALOG_DATABASE_URL")
    or os.getenv("PRODUCT_SOURCES_DATABASE_URL")
    or os.getenv("PG_DATABASE_URL")
  )
  if env_url:
    return env_url

  if pg_config.get("url"):
    return pg_config["url"]

  host = pg_config.get("host", "localhost")
  port = pg_config.get("port", "5432")
  user = pg_config["user"]
  password = pg_config["password"]
  name = pg_config["name"]
  return "host={} port={} user={} password={} dbname={}".format(
    host, port, user, password, name
  )


class CatalogEbayProductsSource:
  """Yield Ebay listings joined with master catalog price/availability."""

  def __init__(self, pg_config, fetch_size=5000):
    if not pg_config:
      raise ValueError(
        "Missing [pg_db] config (expected name=em-catalog and "
        "product_sources_table=product_sources)."
      )
    self.pg_config = pg_config
    self.fetch_size = fetch_size
    table_name = pg_config.get("product_sources_table", "product_sources")
    if not _TABLE_NAME_RE.match(table_name):
      raise ValueError("Invalid product_sources_table: {}".format(table_name))
    self.table_name = table_name

  def iter_products(self, marketplace="us", limit=0):
    source = "Ebay_{}".format(marketplace.upper())
    query = (
      "SELECT ps.product_id, ps.source_product_id, ps.handle, "
      "pc.variant_id, pc.price, pc.availability "
      "FROM {} ps "
      "JOIN product_catalogs pc "
      "  ON pc.product_id = ps.product_id AND pc.is_master IS TRUE "
      "WHERE ps.source = %s "
      "ORDER BY ps.id"
    ).format(self.table_name)
    if limit and int(limit) > 0:
      query = query + " LIMIT %s"

    conn = psycopg2.connect(build_pg_dsn(self.pg_config))
    try:
      with conn.cursor(name="ebay_catalog_{}".format(source.lower())) as cur:
        cur.itersize = self.fetch_size
        if limit and int(limit) > 0:
          cur.execute(query, (source, int(limit)))
        else:
          cur.execute(query, (source,))
        for row in cur:
          product_id, source_product_id, handle, variant_id, price, availability = row
          if not product_id or not source_product_id:
            continue
          yield {
            "product_id": str(product_id),
            "source": source,
            "source_product_id": str(source_product_id),
            "handle": handle or "",
            "variants": [{"variant_id": str(variant_id)}] if variant_id else [],
            "variant_id": str(variant_id) if variant_id else "",
            "catalog_price": price,
            "catalog_availability": availability or "",
            "in_stock": "true"
            if (availability or "").lower().replace(" ", "_") in ("in_stock", "instock")
            else "false",
          }
    finally:
      conn.close()
