# -*- coding: utf-8 -*-

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
    return "host={} port={} user={} password={} dbname={}".format(
        pg_config.get("host", "localhost"),
        pg_config.get("port", "5432"),
        pg_config["user"],
        pg_config["password"],
        pg_config["name"],
    )


class CatalogEbayProductsSource:
    """Stream Ebay rows from em-catalog product_sources + product_catalogs."""

    def __init__(self, pg_config, fetch_size=5000):
        if not pg_config:
            raise ValueError("Missing [pg_db] config")
        self.pg_config = pg_config
        self.fetch_size = fetch_size
        table_name = pg_config.get("product_sources_table", "product_sources")
        if not _TABLE_NAME_RE.match(table_name):
            raise ValueError("Invalid product_sources_table: {}".format(table_name))
        self.table_name = table_name

    def _source_name(self, marketplace):
        return "Ebay_{}".format(marketplace.upper())

    def iter_products(self, marketplace="us", limit=0):
        source = self._source_name(marketplace)
        query = (
            "SELECT ps.product_id, ps.source_product_id, ps.handle, "
            "pc.variant_id, pc.price, pc.availability "
            "FROM {} ps "
            "JOIN product_catalogs pc "
            "  ON pc.product_id = ps.product_id AND pc.is_master IS TRUE "
            "WHERE ps.source = %s "
            "ORDER BY ps.id"
        ).format(self.table_name)
        params = [source]
        if limit and int(limit) > 0:
            query += " LIMIT %s"
            params.append(int(limit))

        conn = psycopg2.connect(build_pg_dsn(self.pg_config))
        try:
            with conn.cursor(name="ebay_catalog_{}".format(source.lower())) as cur:
                cur.itersize = self.fetch_size
                cur.execute(query, tuple(params))
                for row in cur:
                    yield self._row_to_product(row, source)
        finally:
            conn.close()

    def lookup_by_ids(self, marketplace, product_ids=None, source_product_ids=None):
        """Batch lookup catalog rows by Spree product_id and/or Ebay item id."""
        source = self._source_name(marketplace)
        out = {}
        product_ids = [str(x) for x in (product_ids or []) if x not in (None, "")]
        source_product_ids = [
            str(x) for x in (source_product_ids or []) if x not in (None, "")
        ]
        if not product_ids and not source_product_ids:
            return out

        clauses = []
        params = [source]
        if product_ids:
            clauses.append(
                "ps.product_id = ANY(%s::bigint[])"
            )
            params.append(product_ids)
        if source_product_ids:
            clauses.append("ps.source_product_id = ANY(%s::text[])")
            params.append(source_product_ids)
        where_extra = " OR ".join(clauses)
        query = (
            "SELECT ps.product_id, ps.source_product_id, ps.handle, "
            "pc.variant_id, pc.price, pc.availability "
            "FROM {} ps "
            "JOIN product_catalogs pc "
            "  ON pc.product_id = ps.product_id AND pc.is_master IS TRUE "
            "WHERE ps.source = %s AND ({})"
        ).format(self.table_name, where_extra)

        conn = psycopg2.connect(build_pg_dsn(self.pg_config))
        try:
            with conn.cursor() as cur:
                cur.execute(query, tuple(params))
                for row in cur:
                    prod = self._row_to_product(row, source)
                    out[prod["product_id"]] = prod
                    out[prod["source_product_id"]] = prod
        finally:
            conn.close()
        return out

    @staticmethod
    def _row_to_product(row, source):
        product_id, source_product_id, handle, variant_id, price, availability = row
        return {
            "product_id": str(product_id),
            "source": source,
            "source_product_id": str(source_product_id),
            "handle": handle or "",
            "variant_id": str(variant_id) if variant_id else "",
            "variants": [{"variant_id": str(variant_id)}] if variant_id else [],
            "catalog_price": price,
            "catalog_availability": availability or "",
        }
