# -*- coding: utf-8 -*-

from em_ebay_repricer.spree.models import Store


class StoreUtil:
    stores = {}

    @classmethod
    def get_store_by_code(cls, store_code):
        if store_code not in cls.stores:
            cls.stores[store_code] = Store.get_or_none(Store.code == store_code)
        return cls.stores[store_code]
