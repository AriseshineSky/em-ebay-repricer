# -*- coding: utf-8 -*-

from em_ebay_repricer.runtime import logger
from em_ebay_repricer.spree.api import SpreeApi


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
                    continue

                price = round(float(v_offer["price"]), 2)
                currency = v_offer.get("currency", "USD")
                quantity = round(float(v_offer["quantity"]), 2)
                target_offer = {
                    "product_id": product_id_int,
                    "variant_id": variant_id_int,
                    "price": price,
                    "quantity": quantity,
                    "currency": currency,
                }
                if quantity > 0 and "src_price" in v_offer:
                    target_offer.update(
                        {
                            "cost_price": round(float(v_offer["src_price"]), 2),
                            "cost_currency": currency,
                        }
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
        if isinstance(resp, dict) and resp.get("status") == 500:
            logger.error("[InventoryUpdated] Spree set_offers failed: %s", resp)
        else:
            logger.info("[InventoryUpdated] %s", resp)
        return store_offers
