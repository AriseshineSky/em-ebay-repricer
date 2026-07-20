# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import os

import click

from runtime import get_config, logger
from em_ebay_repricer.es_client import EsProductClient
from em_ebay_repricer.pipeline import run_tiers
from em_ebay_repricer.price_calculator import PriceCalculator
from em_ebay_repricer.repricer import EbayRepricer
from em_ebay_repricer.sources import CatalogEbayProductsSource, resolve_tiers
from em_ebay_repricer.spree.models import init_store
from em_ebay_repricer.spree.product_util import ProductUtil
from em_ebay_repricer.spree.store_util import StoreUtil


def _resolve_spree_credentials(cfg, store_code):
    spree_cfg = cfg.get("spree") or {}
    if spree_cfg.get("endpoint") and spree_cfg.get("api_key"):
        return (
            spree_cfg["endpoint"],
            spree_cfg["api_key"],
            spree_cfg.get("api_version", "v1"),
        )

    store_db = cfg.get("store_db")
    if not store_db:
        raise click.ClickException(
            "Provide [spree] endpoint+api_key or [store_db] for store_code lookup"
        )
    init_store(
        store_db["host"],
        store_db["user"],
        store_db["password"],
        store_db["name"],
    )
    store = StoreUtil.get_store_by_code(store_code)
    if not store:
        raise click.ClickException("Store not found: {}".format(store_code))
    cred = json.loads(store.api_credential)
    return cred["endpoint"], cred["api_key"], cred.get("api_version", "v1")


@click.command("em-ebay-repricer")
@click.option("-s", "--store_code", required=True, type=str)
@click.option(
    "-g",
    "--gcs_service_account_path",
    type=str,
    default="~/.em_ebay_repricer/gcs-sa.json",
    show_default=True,
    help="GCS SA JSON for cart/ads seeds.",
)
@click.option("-m", "--marketplace", type=str, default="us", show_default=True)
@click.option("-t", "--ttl", type=int, default=30, show_default=True)
@click.option(
    "--tiers",
    "tiers_arg",
    multiple=True,
    help="Tiers: cart, ads, catalog. Default all. e.g. --tiers cart,ads",
)
@click.option("--dry-run", is_flag=True, help="Calculate only; do not call set_offers.")
@click.option("--limit", type=int, default=0, help="Max products per tier (0 = all).")
@click.option("--batch-size", type=int, default=250, show_default=True)
@click.option("--config", "config_path", type=str, default=None)
def reprice(
    store_code,
    gcs_service_account_path,
    marketplace,
    ttl,
    tiers_arg,
    dry_run,
    limit,
    batch_size,
    config_path,
):
    """Reprice Spree Ebay products from cart, ads, and catalog sources."""
    marketplace = marketplace.lower()
    cfg = get_config(config_path)

    try:
        tiers = resolve_tiers(tiers_arg)
    except ValueError as e:
        raise click.ClickException(str(e))

    pg_config = cfg.get("pg_db")
    if not pg_config:
        raise click.ClickException("Missing [pg_db] in config")

    product_cfg = cfg.get("product_service")
    if not product_cfg:
        raise click.ClickException("Missing [product_service] in config")

    price_rules = {"roi": 0.3, "ad_cost": 5, "transfer_cost": 1}
    for k, v in (cfg.get("price.rules.ebay_{}".format(marketplace), {}) or {}).items():
        try:
            price_rules[k] = round(float(v), 2)
        except (TypeError, ValueError):
            pass

    endpoint, api_key, api_version = _resolve_spree_credentials(cfg, store_code)
    product_util = ProductUtil(endpoint, api_key, api_version)
    product_service = EsProductClient(
        product_cfg["host"],
        product_cfg.get("port", "9200"),
        product_cfg["user"],
        product_cfg["password"],
    )
    price_calculator = PriceCalculator(price_rules)
    catalog_source = CatalogEbayProductsSource(pg_config)
    repricer = EbayRepricer(
        product_service=product_service,
        price_calculator=price_calculator,
        product_util=product_util,
        marketplace=marketplace,
        ttl=ttl,
        dry_run=dry_run,
        batch_size=batch_size,
    )

    gcs_path = os.path.expanduser(gcs_service_account_path) if gcs_service_account_path else None
    run_tiers(
        tiers=tiers,
        marketplace=marketplace,
        catalog_source=catalog_source,
        gcs_service_account_path=gcs_path,
        repricer=repricer,
        limit=limit,
    )
    stats = repricer.stats
    logger.info(
        "[EbayRepricerDone] dry_run=%s products=%s updated=%s in_stock=%s "
        "out_of_stock=%s filtered=%s missing_es=%s skipped_incomplete=%s",
        dry_run,
        stats["products_cnt"],
        stats["updated_cnt"],
        stats["in_stock"],
        stats["out_of_stock"],
        stats["filtered"],
        stats["missing_es"],
        stats["skipped_incomplete"],
    )


if __name__ == "__main__":
    reprice()
