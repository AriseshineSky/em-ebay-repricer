# -*- coding: utf-8 -*-

"""Write Ebay repricer run metrics to Elasticsearch."""

from __future__ import annotations

import datetime
import uuid

from em_ebay_repricer.frequency import DEFAULT_PRICE_DIFF_THRESHOLD
from em_ebay_repricer.runtime import logger
from em_ebay_repricer.sources.tiers import ALL_TIERS

METRICS_INDEX = "ebay_repricer_metrics"


def normalize_tiers(tiers=None):
    if not tiers:
        return []
    selected = {str(t).strip().lower() for t in tiers if t}
    return [tier for tier in ALL_TIERS if tier in selected]


def run_kind_for_tiers(tiers):
    ordered = normalize_tiers(tiers)
    if not ordered:
        return "unknown"
    if ordered == list(ALL_TIERS):
        return "all"
    if len(ordered) == 1:
        return ordered[0]
    return ",".join(ordered)


def save_repricer_metrics(
    product_service,
    store_code,
    marketplace,
    stats,
    start_time,
    end_time,
    tier_stats=None,
    error=None,
    dry_run=False,
    plan=False,
    plan_run_id=None,
    price_diff_threshold=DEFAULT_PRICE_DIFF_THRESHOLD,
    tiers=None,
):
    try:
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        started_at = (
            start_time.replace(tzinfo=datetime.timezone.utc)
            if start_time.tzinfo is None
            else start_time.astimezone(datetime.timezone.utc)
        )
        finished_at = (
            end_time.replace(tzinfo=datetime.timezone.utc)
            if end_time.tzinfo is None
            else end_time.astimezone(datetime.timezone.utc)
        )
        duration_ms = int((finished_at - started_at).total_seconds() * 1000)

        products_cnt = int(stats.get("products_cnt", 0) or 0)
        updated_cnt = int(stats.get("updated_cnt", 0) or 0)
        planned_cnt = int(stats.get("planned_cnt", 0) or 0)
        skipped_price = int(stats.get("skipped_price", 0) or 0)
        skipped_fresh = int(stats.get("skipped_fresh", 0) or 0)
        skipped_incomplete = int(stats.get("skipped_incomplete", 0) or 0)
        skipped_discontinued = int(stats.get("skipped_discontinued", 0) or 0)
        expired_cnt = int(stats.get("expired_cnt", 0) or 0)
        failed_cnt = int(stats.get("failed_cnt", 0) or 0)
        http_5xx_cnt = int(stats.get("http_5xx_cnt", 0) or 0)
        http_5xx_batches = int(stats.get("http_5xx_batches", 0) or 0)
        in_stock = int(stats.get("in_stock", 0) or 0)
        out_of_stock = int(stats.get("out_of_stock", 0) or 0)
        missing_es = int(stats.get("missing_es", 0) or 0)
        filtered = stats.get("filtered") or {}
        if not isinstance(filtered, dict):
            filtered = {}
        filtered_cnt = int(stats.get("filtered_cnt", 0) or 0)
        if filtered_cnt <= 0 and filtered:
            filtered_cnt = sum(int(v or 0) for v in filtered.values())

        ordered_tiers = normalize_tiers(tiers)
        if not ordered_tiers and isinstance(tier_stats, dict) and tier_stats:
            ordered_tiers = normalize_tiers(tier_stats.keys())
        run_kind = run_kind_for_tiers(ordered_tiers)

        is_dry_run = bool(dry_run)
        is_plan = bool(plan) and not is_dry_run
        if is_plan:
            source = "ebay_repricer_plan"
            id_prefix = "ebay_repricer_plan"
            metric_kind = "plan"
            change_cnt = planned_cnt
        elif is_dry_run:
            source = "ebay_repricer_dry_run"
            id_prefix = "ebay_repricer_dry_run"
            metric_kind = "precheck"
            change_cnt = planned_cnt or updated_cnt
        else:
            source = "ebay_repricer"
            id_prefix = "ebay_repricer"
            metric_kind = "final"
            change_cnt = updated_cnt

        error_text = str(error) if error else None
        if error_text and failed_cnt <= 0 and http_5xx_cnt <= 0:
            run_status = "failed"
        elif failed_cnt > 0 or http_5xx_cnt > 0:
            run_status = "partial"
        else:
            run_status = "finished"

        metric_doc = {
            "_id": "{}_{}_{}_{}_{}".format(
                id_prefix,
                marketplace,
                run_kind.replace(",", "-"),
                now_utc.strftime("%Y%m%d%H%M%S"),
                uuid.uuid4().hex[:8],
            ),
            "source": source,
            "task_name": source,
            "store_code": store_code,
            "marketplace": marketplace,
            "tiers": ordered_tiers,
            "run_kind": run_kind,
            "dry_run": is_dry_run,
            "plan": is_plan,
            "metric_kind": metric_kind,
            "timestamp": now_utc.isoformat(),
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "duration_ms": duration_ms,
            "products_cnt": products_cnt,
            "updated_cnt": change_cnt,
            "planned_cnt": planned_cnt,
            "skipped_price": skipped_price,
            "skipped_fresh": skipped_fresh,
            "skipped_incomplete": skipped_incomplete,
            "skipped_discontinued": skipped_discontinued,
            "expired_cnt": expired_cnt,
            "failed_cnt": failed_cnt,
            "http_5xx_cnt": http_5xx_cnt,
            "http_5xx_batches": http_5xx_batches,
            "in_stock": in_stock,
            "out_of_stock": out_of_stock,
            "missing_es": missing_es,
            "filtered": filtered,
            "filtered_cnt": filtered_cnt,
            "tier_stats": tier_stats or {},
            "error": error_text,
            "status": run_status,
            "price_diff_threshold": float(price_diff_threshold),
            "price_change_cnt": change_cnt,
            "unchanged_price_cnt": skipped_price,
            "success_cnt": max(
                products_cnt - skipped_incomplete - skipped_discontinued - failed_cnt,
                0,
            ),
            "success_rate_pct": round(
                (
                    max(
                        products_cnt
                        - skipped_incomplete
                        - skipped_discontinued
                        - failed_cnt,
                        0,
                    )
                    * 100.0
                    / products_cnt
                ),
                2,
            )
            if products_cnt
            else 0.0,
        }
        if plan_run_id:
            metric_doc["plan_run_id"] = str(plan_run_id)
        product_service.ensure_index(METRICS_INDEX)
        product_service.save_products(METRICS_INDEX, [metric_doc])
    except Exception as e:
        logger.exception(e)
