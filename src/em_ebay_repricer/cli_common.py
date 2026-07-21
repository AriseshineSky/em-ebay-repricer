# -*- coding: utf-8 -*-

"""Shared CLI bootstrap for live / plan Ebay repricer commands."""

from __future__ import annotations

import datetime
import json
import os
import uuid

import click

from em_ebay_repricer.es_client import EsProductClient
from em_ebay_repricer.frequency import resolve_price_diff_threshold
from em_ebay_repricer.metrics import save_repricer_metrics
from em_ebay_repricer.pipeline import run_tiers
from em_ebay_repricer.price_calculator import PriceCalculator
from em_ebay_repricer.repricer import EbayRepricer
from em_ebay_repricer.runtime import get_config, logger
from em_ebay_repricer.sources import CatalogEbayProductsSource, resolve_tiers
from em_ebay_repricer.spree.models import init_store
from em_ebay_repricer.spree.product_util import ProductUtil
from em_ebay_repricer.spree.store_util import StoreUtil


def resolve_spree_credentials(cfg, store_code):
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


def build_common(
    store_code,
    marketplace,
    tiers_arg,
    config_path,
    ttl,
    dry_run,
    batch_size,
    mode,
    force=False,
    price_diff_threshold=None,
    need_spree=True,
):
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

    try:
        threshold = resolve_price_diff_threshold(cfg, override=price_diff_threshold)
    except ValueError as e:
        raise click.ClickException(str(e))

    price_rules = {"roi": 0.3, "ad_cost": 5, "transfer_cost": 1}
    for k, v in (cfg.get("price.rules.ebay_{}".format(marketplace), {}) or {}).items():
        try:
            price_rules[k] = round(float(v), 2)
        except (TypeError, ValueError):
            pass

    product_util = None
    if need_spree:
        endpoint, api_key, api_version = resolve_spree_credentials(cfg, store_code)
        product_util = ProductUtil(endpoint, api_key, api_version)

    product_service = EsProductClient(
        product_cfg["host"],
        product_cfg.get("port", "9200"),
        product_cfg["user"],
        product_cfg["password"],
    )
    price_calculator = PriceCalculator(price_rules)
    catalog_source = CatalogEbayProductsSource(pg_config)
    plan_run_id = uuid.uuid4().hex
    repricer = EbayRepricer(
        product_service=product_service,
        price_calculator=price_calculator,
        product_util=product_util,
        marketplace=marketplace,
        store_code=store_code,
        ttl=ttl,
        dry_run=dry_run,
        batch_size=batch_size,
        mode=mode,
        force=force,
        price_diff_threshold=threshold,
        plan_run_id=plan_run_id,
    )
    return {
        "cfg": cfg,
        "tiers": tiers,
        "marketplace": marketplace,
        "catalog_source": catalog_source,
        "repricer": repricer,
        "product_service": product_service,
        "product_util": product_util,
        "threshold": threshold,
        "plan_run_id": plan_run_id,
    }


def run_reprice_command(
    *,
    store_code,
    gcs_service_account_path,
    marketplace,
    ttl,
    tiers_arg,
    dry_run,
    limit,
    batch_size,
    config_path,
    mode,
    force=False,
    price_diff_threshold=None,
    plan=False,
):
    common = build_common(
        store_code=store_code,
        marketplace=marketplace,
        tiers_arg=tiers_arg,
        config_path=config_path,
        ttl=ttl,
        dry_run=dry_run,
        batch_size=batch_size,
        mode=mode,
        force=force,
        price_diff_threshold=price_diff_threshold,
        need_spree=(mode == EbayRepricer.MODE_LIVE),
    )
    gcs_path = (
        os.path.expanduser(gcs_service_account_path) if gcs_service_account_path else None
    )
    start = datetime.datetime.now(datetime.timezone.utc)
    error = None
    tier_stats = {}
    try:
        tier_stats = run_tiers(
            tiers=common["tiers"],
            marketplace=common["marketplace"],
            catalog_source=common["catalog_source"],
            gcs_service_account_path=gcs_path,
            repricer=common["repricer"],
            limit=limit,
        )
    except Exception as e:
        error = e
        logger.exception(e)
    end = datetime.datetime.now(datetime.timezone.utc)

    save_repricer_metrics(
        product_service=common["product_service"],
        store_code=store_code,
        marketplace=common["marketplace"],
        stats=common["repricer"].stats,
        start_time=start,
        end_time=end,
        tier_stats=tier_stats,
        error=error,
        dry_run=dry_run,
        plan=plan,
        plan_run_id=common["plan_run_id"],
        price_diff_threshold=common["threshold"],
        tiers=common["tiers"],
    )
    stats = common["repricer"].stats
    logger.info(
        "[EbayRepricerDone] mode=%s dry_run=%s products=%s planned=%s updated=%s "
        "skipped_fresh=%s skipped_price=%s filtered=%s missing_es=%s",
        mode,
        dry_run,
        stats["products_cnt"],
        stats["planned_cnt"],
        stats["updated_cnt"],
        stats["skipped_fresh"],
        stats["skipped_price"],
        stats["filtered"],
        stats["missing_es"],
    )
    if error:
        raise click.ClickException(str(error))
    return common
