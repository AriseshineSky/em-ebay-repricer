# -*- coding: utf-8 -*-

"""Price-diff skip and freshness helpers."""

from __future__ import annotations

import datetime

import dateparser

DEFAULT_PRICE_DIFF_THRESHOLD = 1.0
CONFIG_SECTION = "ebay_repricer"
CONFIG_KEY = "price_diff_threshold"


def resolve_price_diff_threshold(cfg=None, override=None):
    """Resolve skip threshold: CLI override > config > default ($1)."""
    if override is not None and override != "":
        value = float(override)
    else:
        section = (cfg or {}).get(CONFIG_SECTION) or {}
        raw = section.get(CONFIG_KEY)
        value = DEFAULT_PRICE_DIFF_THRESHOLD if raw in (None, "") else float(raw)
    if value < 0:
        raise ValueError("{} must be >= 0, got {}".format(CONFIG_KEY, value))
    return value


def should_skip_by_price_diff(
    current_price, new_price, threshold=DEFAULT_PRICE_DIFF_THRESHOLD, force=False
):
    """Return True when absolute price delta is below threshold."""
    if force:
        return False
    if current_price is None or new_price is None:
        return False
    try:
        return abs(float(current_price) - float(new_price)) < float(threshold)
    except (TypeError, ValueError):
        return False


def current_catalog_price(product):
    """Prefer enrich catalog_price; else master/first variant price."""
    if product is None:
        return None
    if product.get("catalog_price") not in (None, ""):
        try:
            return float(product["catalog_price"])
        except (TypeError, ValueError):
            pass
    variants = product.get("variants") or []
    for variant in variants:
        if variant.get("is_master") and variant.get("price") not in (None, ""):
            try:
                return float(variant["price"])
            except (TypeError, ValueError):
                pass
    if variants and variants[0].get("price") not in (None, ""):
        try:
            return float(variants[0]["price"])
        except (TypeError, ValueError):
            return None
    return None


def parse_source_datetime(product_or_value):
    """Parse ES source date/time into timezone-aware UTC datetime (or None)."""
    if product_or_value is None:
        return None
    if isinstance(product_or_value, dict):
        raw = product_or_value.get("date", product_or_value.get("time"))
    else:
        raw = product_or_value
    if raw in (None, ""):
        return None
    if isinstance(raw, datetime.datetime):
        dt = raw
    else:
        try:
            dt = dateparser.parse(str(raw))
        except Exception:
            return None
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone(datetime.timezone.utc)


def needs_recalc(source_doc, pending_doc, force=False):
    """True when source crawl time is newer than last calc_at (or missing)."""
    if force:
        return True
    if not pending_doc:
        return True
    calc_at = parse_source_datetime(pending_doc.get("calc_at"))
    if calc_at is None:
        return True
    source_at = parse_source_datetime(source_doc)
    if source_at is None:
        # No parseable source time → allow recalc (caller may still filter/OOS).
        return True
    return source_at > calc_at


def tier_flag_field(tier):
    return "tier_{}".format(str(tier).strip().lower())
