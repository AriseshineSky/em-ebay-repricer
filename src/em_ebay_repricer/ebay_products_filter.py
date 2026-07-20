# -*- coding: utf-8 -*-

import re


class EbayProductsFilterPipeline:
    def __init__(self, max_shipping_days=20, min_seller_rating=98):
        self.max_shipping_days = max_shipping_days
        self.min_seller_rating = min_seller_rating
        self.expire_used_pattern = re.compile(r".*(expir|used|open in box).*")
        self.source = "Ebay_US"

    def check_product(self, product):
        exist = product.get("existence", True)
        if not exist:
            return {"passed": False, "reason": "NotExist", "message": "Not Exist"}

        available_qty = product.get("available_qty", None)
        if available_qty == 0:
            return {
                "passed": False,
                "reason": "NotAvailable",
                "message": "Not available now",
            }
        if available_qty and available_qty < 3:
            return {
                "passed": False,
                "reason": "LowInventory",
                "message": "Available quantity is lower than 3",
            }

        has_only_default_variant = product.get("has_only_default_variant", True)
        if not has_only_default_variant:
            return {
                "passed": False,
                "reason": "MultipleVariant",
                "message": "Multiple Variants",
            }

        seller_rating = product.get("seller_rating", 0)
        if seller_rating and seller_rating < self.min_seller_rating:
            return {
                "passed": False,
                "reason": "SellerRatingInvalid",
                "message": "Seller rating too low",
            }

        title = (product.get("title") or "").lower()
        if self.expire_used_pattern.match(title):
            return {
                "passed": False,
                "reason": "UsedOrExpire",
                "message": "Used or expire title",
            }

        return {"passed": True, "reason": ""}
