# -*- coding: utf-8 -*-

"""Shared orchestration for cart / ads / catalog Ebay reprice tiers."""

from __future__ import annotations

from pathlib import Path

from em_ebay_repricer.gcs_helper import GCSHelper
from em_ebay_repricer.runtime import logger
from em_ebay_repricer.sources import (
    TIER_ADS,
    TIER_CART,
    TIER_CATALOG,
    SeedFileDataSource,
)

BUCKET_NAME = "em-bucket"
CART_SEED_BLOB_TEMPLATE = "em-analytics/carts/sources/EBAY_{}.txt"
ADS_SEED_BLOB_TEMPLATE = "em-analytics/sources/EBAY_{}.txt"
LOCAL_CART_SEED_TEMPLATE = "tmp/gcs/carts/ebay_{}.txt"
LOCAL_ADS_SEED_TEMPLATE = "tmp/gcs/ads/ebay_{}.txt"


def download_seed(gcs_helper, blob_name, local_path):
    local_path = Path(local_path)
    ok = gcs_helper.download_file(blob_name, local_path)
    if ok and local_path.is_file():
        return SeedFileDataSource(local_path)
    return None


def extract_ids(record):
    if not record:
        return None, None
    pid = record.get("product_id")
    spid = record.get("source_product_id") or record.get("ebay_id") or record.get("id")
    return (
        str(pid) if pid not in (None, "") else None,
        str(spid) if spid not in (None, "") else None,
    )


def _snapshot_stats(repricer):
    return {
        "products_cnt": int(repricer.stats.get("products_cnt", 0) or 0),
        "updated_cnt": int(repricer.stats.get("updated_cnt", 0) or 0),
        "planned_cnt": int(repricer.stats.get("planned_cnt", 0) or 0),
        "skipped_price": int(repricer.stats.get("skipped_price", 0) or 0),
        "skipped_fresh": int(repricer.stats.get("skipped_fresh", 0) or 0),
        "skipped_incomplete": int(repricer.stats.get("skipped_incomplete", 0) or 0),
        "skipped_discontinued": int(repricer.stats.get("skipped_discontinued", 0) or 0),
        "in_stock": int(repricer.stats.get("in_stock", 0) or 0),
        "out_of_stock": int(repricer.stats.get("out_of_stock", 0) or 0),
        "filtered_cnt": int(repricer.stats.get("filtered_cnt", 0) or 0),
        "expired_cnt": int(repricer.stats.get("expired_cnt", 0) or 0),
    }


def run_tiers(
    tiers,
    marketplace,
    catalog_source,
    gcs_service_account_path,
    repricer,
    limit=0,
):
    marketplace_key = marketplace.lower()
    cart_gcs = None
    ads_gcs = None
    if TIER_CART in tiers or TIER_ADS in tiers:
        if not gcs_service_account_path:
            raise ValueError("GCS service account required for cart/ads tiers")
        cart_gcs = GCSHelper(gcs_service_account_path, BUCKET_NAME, "em-analytics/carts")
        ads_gcs = GCSHelper(gcs_service_account_path, BUCKET_NAME, "em-analytics")

    tier_stats = {}

    for tier in tiers:
        logger.info("[TierStart] %s marketplace=%s", tier, marketplace_key)
        before = _snapshot_stats(repricer)
        processed = 0
        batch = {}
        batch_lookup_pids = []
        batch_lookup_spids = []
        repricer.active_tier = tier

        def flush():
            nonlocal batch, batch_lookup_pids, batch_lookup_spids, processed
            if not batch and not batch_lookup_pids and not batch_lookup_spids:
                return
            need_pid = [p for p in batch_lookup_pids if p]
            need_spid = [s for s in batch_lookup_spids if s]
            lookup = catalog_source.lookup_by_ids(
                marketplace_key, product_ids=need_pid, source_product_ids=need_spid
            )
            enriched = {}
            for key, stub in list(batch.items()):
                prod = (
                    lookup.get(stub.get("product_id") or "")
                    or lookup.get(stub.get("source_product_id") or "")
                    or lookup.get(key)
                )
                if prod:
                    enriched[prod["source_product_id"]] = prod
                elif (
                    stub.get("source_product_id")
                    and stub.get("product_id")
                    and stub.get("handle")
                ):
                    enriched[stub["source_product_id"]] = stub
            repricer.process_batch(enriched, tier=tier)
            processed += len(enriched)
            batch = {}
            batch_lookup_pids = []
            batch_lookup_spids = []

        if tier == TIER_CATALOG:
            for prod in catalog_source.iter_products(marketplace_key, limit=limit):
                batch[prod["source_product_id"]] = prod
                if len(batch) >= repricer.batch_size:
                    flush()
                if limit and processed + len(batch) >= limit:
                    break
            flush()
        elif tier == TIER_CART:
            blob = CART_SEED_BLOB_TEMPLATE.format(marketplace.upper())
            local = Path(LOCAL_CART_SEED_TEMPLATE.format(marketplace_key))
            source = download_seed(cart_gcs, blob, local)
            if source is None:
                logger.warning("[TierSkip] missing seed for %s (%s)", tier, blob)
                tier_stats[tier] = {"processed": 0, "skipped_missing_file": True}
                continue
            for record in source.iter_products(marketplace_key):
                pid, spid = extract_ids(record)
                if not pid and not spid:
                    continue
                key = spid or pid
                stub = {
                    "product_id": pid or "",
                    "source_product_id": spid or "",
                    "handle": record.get("handle") or "",
                    "variants": [],
                }
                if record.get("variant_id"):
                    stub["variant_id"] = str(record["variant_id"])
                    stub["variants"] = [{"variant_id": str(record["variant_id"])}]
                batch[key] = stub
                if pid:
                    batch_lookup_pids.append(pid)
                if spid:
                    batch_lookup_spids.append(spid)
                if len(batch) >= repricer.batch_size:
                    flush()
                if limit and processed + len(batch) >= limit:
                    break
            flush()
        elif tier == TIER_ADS:
            blob = ADS_SEED_BLOB_TEMPLATE.format(marketplace.upper())
            local = Path(LOCAL_ADS_SEED_TEMPLATE.format(marketplace_key))
            source = download_seed(ads_gcs, blob, local)
            if source is None:
                logger.warning("[TierSkip] missing seed for %s (%s)", tier, blob)
                tier_stats[tier] = {"processed": 0, "skipped_missing_file": True}
                continue
            for record in source.iter_products(marketplace_key):
                pid, spid = extract_ids(record)
                if not pid and not spid:
                    continue
                key = spid or pid
                stub = {
                    "product_id": pid or "",
                    "source_product_id": spid or "",
                    "handle": record.get("handle") or "",
                    "variants": [],
                }
                if record.get("variant_id"):
                    stub["variant_id"] = str(record["variant_id"])
                    stub["variants"] = [{"variant_id": str(record["variant_id"])}]
                batch[key] = stub
                if pid:
                    batch_lookup_pids.append(pid)
                if spid:
                    batch_lookup_spids.append(spid)
                if len(batch) >= repricer.batch_size:
                    flush()
                if limit and processed + len(batch) >= limit:
                    break
            flush()
        else:
            raise ValueError("Unknown tier: {}".format(tier))

        after = _snapshot_stats(repricer)
        tier_stats[tier] = {
            "processed": processed,
            "products_cnt": after["products_cnt"] - before["products_cnt"],
            "updated_cnt": after["updated_cnt"] - before["updated_cnt"],
            "planned_cnt": after["planned_cnt"] - before["planned_cnt"],
            "skipped_price": after["skipped_price"] - before["skipped_price"],
            "skipped_fresh": after["skipped_fresh"] - before["skipped_fresh"],
            "in_stock": after["in_stock"] - before["in_stock"],
            "out_of_stock": after["out_of_stock"] - before["out_of_stock"],
            "filtered_cnt": after["filtered_cnt"] - before["filtered_cnt"],
            "expired_cnt": after["expired_cnt"] - before["expired_cnt"],
        }
        logger.info("[TierDone] %s processed~=%s stats=%s", tier, processed, tier_stats[tier])

    repricer.active_tier = None
    return tier_stats
