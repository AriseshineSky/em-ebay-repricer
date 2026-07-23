# -*- coding: utf-8 -*-

from em_ebay_repricer.runtime import logger
from em_ebay_repricer.spree.api import SpreeApi


class SpreeSetOffersError(RuntimeError):
    """Raised when Spree set_offers returns a non-success response."""


def _as_float(value, field_name):
    """Spree 500s when price/cost_price are JSON strings."""
    if value is None:
        raise ValueError("{} is required".format(field_name))
    try:
        return round(float(value), 2)
    except (TypeError, ValueError) as e:
        raise ValueError("{} must be numeric, got {!r}".format(field_name, value)) from e


def _as_int(value, field_name):
    """Inventory quantity must be a JSON integer (not a string)."""
    if value is None:
        raise ValueError("{} is required".format(field_name))
    try:
        return int(round(float(value)))
    except (TypeError, ValueError) as e:
        raise ValueError("{} must be an integer, got {!r}".format(field_name, value)) from e


class ProductUtil:
    def __init__(self, endpoint, api_key, api_version="v1"):
        self.spree_api = SpreeApi(endpoint, api_key, api_version)

    def _build_store_offers(self, prods):
        store_offers = dict()
        for prod_id, prod in prods.items():
            handle = prod.get("handle")
            if not handle:
                logger.warning(
                    "[InventoryUpdate] skip product_id=%s: missing handle", prod_id
                )
                continue
            # Spree historically 500'd on string product_id/variant_id; keep ints.
            try:
                product_id_int = int(prod_id)
            except (TypeError, ValueError):
                logger.warning(
                    "[InventoryUpdate] skip product_id=%s: not an integer id", prod_id
                )
                continue

            store_offer = {
                "handle": handle,
                "product_id": product_id_int,
                "offers": {},
            }
            variants = prod.get("variants") or None
            if not variants:
                continue

            offer = prod.get("offer", None)
            if isinstance(offer, bool) and not offer:
                continue
            if offer is None:
                continue

            if len(variants) > 1:
                if not isinstance(offer, dict):
                    continue
            else:
                v = variants[0]
                vid = str(v["variant_id"])
                if vid not in offer and "price" in offer:
                    offer = {vid: offer}

            for variant in variants:
                vid = str(variant["variant_id"])
                v_offer = offer.get(vid) if isinstance(offer, dict) else None
                if not v_offer:
                    continue
                try:
                    variant_id_int = int(vid)
                except (TypeError, ValueError):
                    logger.warning(
                        "[InventoryUpdate] skip product_id=%s variant_id=%s: not int",
                        prod_id,
                        vid,
                    )
                    continue

                try:
                    price = _as_float(v_offer["price"], "price")
                    quantity = _as_int(v_offer["quantity"], "quantity")
                except (KeyError, ValueError) as e:
                    logger.warning(
                        "[InventoryUpdate] skip product_id=%s variant_id=%s: %s",
                        prod_id,
                        vid,
                        e,
                    )
                    continue

                target_offer = {
                    "product_id": product_id_int,
                    "variant_id": variant_id_int,
                    "price": price,
                    "quantity": quantity,
                    "currency": v_offer.get("currency", "USD"),
                }
                if quantity > 0 and "src_price" in v_offer:
                    try:
                        target_offer["cost_price"] = _as_float(
                            v_offer["src_price"], "cost_price"
                        )
                        target_offer["cost_currency"] = target_offer["currency"]
                    except ValueError as e:
                        logger.warning(
                            "[InventoryUpdate] drop cost_price product_id=%s: %s",
                            prod_id,
                            e,
                        )
                store_offer["offers"][str(variant_id_int)] = target_offer

            if store_offer["offers"]:
                store_offers[str(product_id_int)] = store_offer

        return store_offers

    def set_products_offer(self, prods, pool=None):
        store_offers = self._build_store_offers(prods)
        if not store_offers:
            return store_offers
        resp = self.spree_api.set_offers(store_offers)
        if isinstance(resp, dict) and (
            resp.get("status") == 500
            or (isinstance(resp.get("status"), int) and resp["status"] >= 400)
        ):
            logger.error("[InventoryUpdated] Spree set_offers failed: %s", resp)
            raise SpreeSetOffersError("Spree set_offers failed: {}".format(resp))
        if isinstance(resp, dict) and resp.get("succeed") is False:
            logger.error("[InventoryUpdated] Spree set_offers rejected: %s", resp)
            raise SpreeSetOffersError("Spree set_offers rejected: {}".format(resp))
        logger.info("[InventoryUpdated] %s", resp)
        return store_offers
