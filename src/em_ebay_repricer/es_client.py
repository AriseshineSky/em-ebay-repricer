# -*- coding: utf-8 -*-

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from typing import Any


class EsProductClient:
    """Minimal ES client using _mget (document _id = ebay item id)."""

    def __init__(self, host, port, user, password, timeout=60):
        host = str(host).rstrip("/")
        if host.startswith("http://") or host.startswith("https://"):
            self.base = host
        else:
            self.base = "http://{}:{}".format(host, port)
        token = base64.b64encode(
            "{}:{}".format(user, password).encode("utf-8")
        ).decode("ascii")
        self._auth = "Basic {}".format(token)
        self.timeout = timeout

    def search_products(self, index_name, product_ids):
        if not product_ids:
            return {}
        body = {"docs": [{"_id": str(pid), "_source": True} for pid in product_ids]}
        url = "{}/{}/_mget".format(self.base.rstrip("/"), index_name)
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": self._auth,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")[:300]
            raise RuntimeError("ES HTTP {}: {}".format(e.code, detail)) from e

        out: dict[str, Any] = {}
        for doc in data.get("docs", []):
            if not doc.get("found"):
                continue
            pid = str(doc.get("_id") or "")
            src = doc.get("_source") or {}
            if pid:
                out[pid] = src
        return out
