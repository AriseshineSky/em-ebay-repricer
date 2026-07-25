# -*- coding: utf-8 -*-

"""Persist / load planned Ebay price updates in Elasticsearch."""

from __future__ import annotations

import datetime
import uuid

from em_ebay_repricer.frequency import (
    current_catalog_price,
    parse_source_datetime,
    tier_flag_field,
)
from em_ebay_repricer.runtime import logger

PENDING_INDEX = "ebay_repricer_pending"
STATUS_PENDING = "pending"
STATUS_APPLIED = "applied"
STATUS_FAILED = "failed"
STATUS_SKIPPED_PRICE = "skipped_price"
STATUS_SKIPPED_FRESH = "skipped_fresh"
STATUS_FILTERED = "filtered"

# Apply retries Spree failures as well as fresh pending rows.
APPLY_STATUSES = (STATUS_PENDING, STATUS_FAILED)

PENDING_MAPPINGS = {
    "properties": {
        "status": {"type": "keyword"},
        "store_code": {"type": "keyword"},
        "marketplace": {"type": "keyword"},
        "product_id": {"type": "keyword"},
        "handle": {"type": "keyword"},
        "ebay_id": {"type": "keyword"},
        "tier": {"type": "keyword"},
        "tier_cart": {"type": "boolean"},
        "tier_ads": {"type": "boolean"},
        "tier_catalog": {"type": "boolean"},
        "plan_run_id": {"type": "keyword"},
        "old_price": {"type": "float"},
        "calc_at": {"type": "date"},
        "source_updated_at": {"type": "date"},
        "planned_at": {"type": "date"},
        "applied_at": {"type": "date"},
        "error": {"type": "text"},
        "offer": {"type": "object", "enabled": True},
        "variants": {"type": "object", "enabled": True},
    }
}


def ensure_pending_index(service):
    return service.ensure_index(PENDING_INDEX, mappings=PENDING_MAPPINGS)


def pending_doc_id(store_code, marketplace, product_id):
    return "{}_{}_{}".format(store_code, marketplace.lower(), product_id)


def _tier_flags(existing, tier):
    flags = {
        "tier_cart": bool((existing or {}).get("tier_cart")),
        "tier_ads": bool((existing or {}).get("tier_ads")),
        "tier_catalog": bool((existing or {}).get("tier_catalog")),
    }
    field = tier_flag_field(tier) if tier else None
    if field in flags:
        flags[field] = True
    return flags


def _variants_payload(prod):
    variants = []
    for variant in prod.get("variants") or []:
        if variant.get("variant_id") is None:
            continue
        variants.append(
            {
                "variant_id": str(variant["variant_id"]),
                "is_master": bool(variant.get("is_master", True)),
                "price": variant.get("price"),
                "quantity": variant.get("quantity"),
                "currency": variant.get("currency"),
            }
        )
    return variants


def build_pending_doc(
    store_code,
    marketplace,
    prod,
    *,
    status,
    tier=None,
    plan_run_id=None,
    existing=None,
    source_doc=None,
    update_calc_at=True,
):
    """Build one pending upsert document for a store product."""
    offer = prod.get("offer") or {}
    if not isinstance(offer, dict) or "price" not in offer:
        return None
    variants = _variants_payload(prod)
    if not variants:
        return None

    product_id = str(prod.get("product_id"))
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    plan_run_id = plan_run_id or uuid.uuid4().hex
    flags = _tier_flags(existing, tier)
    source_updated_at = None
    src_dt = parse_source_datetime(source_doc)
    if src_dt is not None:
        source_updated_at = src_dt.isoformat()

    doc = {
        "_id": pending_doc_id(store_code, marketplace, product_id),
        "status": status,
        "store_code": store_code,
        "marketplace": marketplace.lower(),
        "product_id": product_id,
        "handle": prod.get("handle"),
        "ebay_id": str(prod.get("source_product_id") or ""),
        "tier": tier,
        "old_price": current_catalog_price(prod),
        "offer": {
            "price": offer.get("price"),
            "quantity": offer.get("quantity"),
            "currency": offer.get("currency", "USD"),
            "src_price": offer.get("src_price"),
            "src_currency": offer.get("src_currency"),
        },
        "variants": variants,
        "planned_at": now,
        "applied_at": None,
        "error": None,
        "plan_run_id": plan_run_id,
        "source_updated_at": source_updated_at,
    }
    doc.update(flags)
    if update_calc_at:
        doc["calc_at"] = now
    elif existing and existing.get("calc_at"):
        doc["calc_at"] = existing.get("calc_at")
    return doc


def build_tier_only_patch(existing, tier, store_code, marketplace, product_id):
    """Patch body when source is fresh — only OR tier flags / last tier."""
    if not tier:
        return None, None
    flags = _tier_flags(existing, tier)
    doc_id = pending_doc_id(store_code, marketplace, product_id)
    body = {"doc": {"tier": tier, **flags}}
    return doc_id, body


def save_pending_docs(service, docs):
    if not docs:
        return True
    if not ensure_pending_index(service):
        logger.error("[PendingStore] ensure_index failed for %s", PENDING_INDEX)
        return False
    ok = service.save_products(PENDING_INDEX, docs)
    if ok:
        logger.info("[PendingStore] upserted %s docs into %s", len(docs), PENDING_INDEX)
    return ok


def mget_pending(service, store_code, marketplace, product_ids):
    """Return pending _id -> _source for known product_ids."""
    if not product_ids:
        return {}
    ids = [
        pending_doc_id(store_code, marketplace, pid) for pid in product_ids if pid
    ]
    return service.search_products(PENDING_INDEX, ids)


def normalize_apply_statuses(status=None):
    """Normalize status / statuses for ES filter (term or terms)."""
    if status is None:
        return list(APPLY_STATUSES)
    if isinstance(status, (list, tuple, set)):
        values = [str(s).strip() for s in status if str(s).strip()]
    else:
        values = [str(status).strip()] if str(status).strip() else []
    if not values:
        return list(APPLY_STATUSES)
    # Preserve order, drop duplicates.
    seen = set()
    out = []
    for value in values:
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out


def _status_filter(statuses):
    if len(statuses) == 1:
        return {"term": {"status": statuses[0]}}
    return {"terms": {"status": statuses}}


def iter_pending_docs(
    service,
    store_code,
    marketplace,
    limit=0,
    status=None,
    batch_size=100,
):
    """Yield pending ES hits for apply (default: pending + failed)."""
    fetched = 0
    statuses = normalize_apply_statuses(status)
    query = {
        "bool": {
            "filter": [
                _status_filter(statuses),
                {"term": {"store_code": store_code}},
                {"term": {"marketplace": marketplace.lower()}},
            ]
        }
    }
    for hit in service.scan(PENDING_INDEX, query=query, size=batch_size):
        yield hit
        fetched += 1
        if limit and fetched >= limit:
            break


def pending_hit_to_product(hit):
    src = hit.get("_source") or hit
    product_id = str(src.get("product_id"))
    return product_id, {
        "product_id": product_id,
        "handle": src.get("handle"),
        "source_product_id": src.get("ebay_id"),
        "variants": src.get("variants") or [],
        "offer": src.get("offer") or {},
    }


def mark_pending_status(service, doc_ids, status, error=None):
    if not doc_ids:
        return True
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    body = {"doc": {"status": status, "applied_at": now, "error": error}}
    return service.update_docs(PENDING_INDEX, doc_ids, body)


def apply_tier_patches(service, patches):
    """patches: list of (doc_id, update_body)."""
    if not patches:
        return True
    # Group identical bodies is rare; apply one-by-one via bulk lines.
    # Reuse update_docs only when body identical — here bodies differ by flags.
    lines_docs = []
    for doc_id, body in patches:
        # fabricate single-id update via save of full merge is wrong; use bulk update
        lines_docs.append((doc_id, body))
    # Build NDJSON through update_docs per unique body groups
    by_key = {}
    for doc_id, body in lines_docs:
        key = json_dumps_stable(body)
        by_key.setdefault(key, {"body": body, "ids": []})
        by_key[key]["ids"].append(doc_id)
    ok = True
    for group in by_key.values():
        if not service.update_docs(PENDING_INDEX, group["ids"], group["body"]):
            ok = False
    return ok


def json_dumps_stable(obj):
    import json

    return json.dumps(obj, sort_keys=True)
