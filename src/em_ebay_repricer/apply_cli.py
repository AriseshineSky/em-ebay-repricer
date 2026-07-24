# -*- coding: utf-8 -*-

"""CLI: apply pending Ebay price updates from ES to Spree set_offers."""

from __future__ import annotations

import datetime

import click

from em_ebay_repricer.reprice_command import resolve_spree_credentials
from em_ebay_repricer.es_client import EsProductClient
from em_ebay_repricer.metrics import save_repricer_metrics
from em_ebay_repricer.pending_store import (
    STATUS_APPLIED,
    STATUS_FAILED,
    STATUS_PENDING,
    iter_pending_docs,
    mark_pending_status,
    pending_hit_to_product,
)
from em_ebay_repricer.runtime import get_config, logger
from em_ebay_repricer.spree.product_util import ProductUtil, SpreeSetOffersError


@click.command("em-ebay-repricer-apply")
@click.option("-s", "--store_code", required=True, type=str)
@click.option("-m", "--marketplace", type=str, default="us", show_default=True)
@click.option("--limit", type=int, default=0, help="Max pending docs (0 = all).")
@click.option("--batch-size", type=int, default=250, show_default=True)
@click.option("--dry-run", is_flag=True, help="List pending without Spree/status updates.")
@click.option("--config", "config_path", type=str, default=None)
def apply_prices(
    store_code,
    marketplace="us",
    limit=0,
    batch_size=250,
    dry_run=False,
    config_path=None,
):
    """Read status=pending docs and push to Spree set_offers."""
    marketplace = marketplace.lower()
    cfg = get_config(config_path)
    product_cfg = cfg.get("product_service")
    if not product_cfg:
        raise click.ClickException("Missing [product_service] in config")

    product_service = EsProductClient(
        product_cfg["host"],
        product_cfg.get("port", "9200"),
        product_cfg["user"],
        product_cfg["password"],
    )
    product_util = None
    if not dry_run:
        endpoint, api_key, api_version = resolve_spree_credentials(cfg, store_code)
        product_util = ProductUtil(endpoint, api_key, api_version)

    start = datetime.datetime.now(datetime.timezone.utc)
    stats = {
        "products_cnt": 0,
        "updated_cnt": 0,
        "planned_cnt": 0,
        "skipped_price": 0,
        "skipped_fresh": 0,
        "failed_cnt": 0,
        "http_5xx_cnt": 0,
        "http_5xx_batches": 0,
    }
    error = None
    last_5xx_error = None
    batch = {}
    batch_ids = []

    def flush():
        nonlocal batch, batch_ids, last_5xx_error
        if not batch:
            return
        if dry_run:
            for pid, prod in batch.items():
                offer = prod.get("offer") or {}
                logger.info(
                    "[ApplyDryRun] product_id=%s ebay_id=%s price=%s qty=%s",
                    pid,
                    prod.get("source_product_id"),
                    offer.get("price"),
                    offer.get("quantity"),
                )
            stats["updated_cnt"] += len(batch)
            batch = {}
            batch_ids = []
            return
        try:
            product_util.set_products_offer(batch, None)
            mark_pending_status(product_service, batch_ids, STATUS_APPLIED)
            stats["updated_cnt"] += len(batch)
        except SpreeSetOffersError as e:
            logger.exception(e)
            mark_pending_status(
                product_service, batch_ids, STATUS_FAILED, error=str(e)[:500]
            )
            n = len(batch)
            stats["failed_cnt"] += n
            if e.is_5xx:
                stats["http_5xx_cnt"] += n
                stats["http_5xx_batches"] += 1
                last_5xx_error = str(e)[:500]
                logger.error(
                    "[EbayRepricerApply] Spree HTTP %s for %s products in batch",
                    e.status,
                    n,
                )
        except Exception as e:
            logger.exception(e)
            mark_pending_status(
                product_service, batch_ids, STATUS_FAILED, error=str(e)[:500]
            )
            stats["failed_cnt"] += len(batch)
        batch = {}
        batch_ids = []

    try:
        for hit in iter_pending_docs(
            product_service,
            store_code,
            marketplace,
            limit=limit,
            status=STATUS_PENDING,
            batch_size=batch_size,
        ):
            stats["products_cnt"] += 1
            doc_id = hit.get("_id")
            pid, prod = pending_hit_to_product(hit)
            if not prod.get("handle") or not prod.get("variants"):
                continue
            batch[pid] = prod
            batch_ids.append(doc_id)
            if len(batch) >= batch_size:
                flush()
        flush()
    except Exception as e:
        error = e
        logger.exception(e)

    end = datetime.datetime.now(datetime.timezone.utc)
    # Surface last Spree 5xx on the run when batches failed but the process continued.
    metrics_error = error or (
        last_5xx_error if stats["http_5xx_cnt"] and not dry_run else None
    )
    save_repricer_metrics(
        product_service=product_service,
        store_code=store_code,
        marketplace=marketplace,
        stats=stats,
        start_time=start,
        end_time=end,
        tier_stats={},
        error=metrics_error,
        dry_run=dry_run,
        plan=False,
        tiers=["cart", "ads", "catalog"],
    )
    logger.info(
        "[EbayRepricerApplyDone] dry_run=%s seen=%s updated=%s failed=%s http_5xx=%s http_5xx_batches=%s",
        dry_run,
        stats["products_cnt"],
        stats["updated_cnt"],
        stats["failed_cnt"],
        stats["http_5xx_cnt"],
        stats["http_5xx_batches"],
    )
    if error:
        raise click.ClickException(str(error))


if __name__ == "__main__":
    apply_prices()
