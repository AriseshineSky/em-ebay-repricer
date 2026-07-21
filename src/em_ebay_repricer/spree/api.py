# -*- coding: utf-8 -*-

from __future__ import annotations

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from em_ebay_repricer.runtime import logger


class SpreeApi:
    def __init__(self, endpoint, api_key, api_version="v1"):
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key
        self.api_version = api_version
        retries = Retry(
            total=7,
            backoff_factor=0.1,
            # Do not retry bare 500s: set_offers is not idempotent-friendly under
            # load, and bad payloads (e.g. string prices) never recover by retry.
            status_forcelist=[429, 502, 503, 504],
        )
        self.session = requests.Session()
        self.session.mount(self.endpoint, HTTPAdapter(max_retries=retries))

    def set_offers(self, product_offers):
        endpoint_url = "{}/api/{}/products/set_offers?token={}".format(
            self.endpoint, self.api_version, self.api_key
        )
        response = self.session.post(
            endpoint_url, json={"offers": product_offers}, timeout=(60, 120)
        )
        logger.debug("[Request] %s", response.request.url)
        try:
            body = response.json()
        except ValueError:
            body = {"status": response.status_code, "error": response.text[:500]}
        if response.status_code >= 400 and isinstance(body, dict) and "status" not in body:
            body = {"status": response.status_code, "error": body}
        return body
