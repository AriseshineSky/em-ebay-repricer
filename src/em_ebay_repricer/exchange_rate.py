# -*- coding: utf-8 -*-

import requests

default_rates = {
    "base": "USD",
    "rates": {
        "USD": 1,
        "CAD": 1.2874,
        "CNY": 6.6093,
        "GBP": 0.7414,
        "EUR": 0.8414,
        "AUD": 1.2994,
        "JPY": 112.49,
        "KRW": 1358.02,
        "AED": 3.67,
    },
}


class ExchangeRate:
    cached_rates = {}

    @classmethod
    def get_exchange_rate(cls, base_currency, currency, endpoint="latest"):
        base_currency = (base_currency or "USD").upper()
        currency = (currency or "USD").upper()
        if base_currency == currency:
            return 1
        cache_key = (base_currency, currency)
        if cache_key in cls.cached_rates:
            return cls.cached_rates[cache_key]
        rate = None
        try:
            resp = requests.get(
                "https://hexarate.paikama.co/api/rates/{}/{}/{}".format(
                    base_currency, currency, endpoint
                ),
                timeout=2,
            )
            if resp.status_code == 200:
                rate = resp.json().get("data", {}).get("mid", None)
        except Exception:
            pass
        if not rate:
            if base_currency == "USD":
                rate = default_rates["rates"].get(currency)
            elif currency == "USD":
                base_rate = default_rates["rates"].get(base_currency)
                if base_rate:
                    rate = 1 / base_rate
        if rate:
            cls.cached_rates[cache_key] = rate
        return rate
