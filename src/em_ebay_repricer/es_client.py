# -*- coding: utf-8 -*-

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from typing import Any, Iterable, Iterator


DEFAULT_INDEX_SETTINGS = {
    "number_of_shards": 1,
    "number_of_replicas": 0,
}


class EsProductClient:
    """Minimal ES client (urllib): mget, bulk upsert, update, scan, ensure_index."""

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

    def _headers(self, content_type=True):
        headers = {
            "Accept": "application/json",
            "Authorization": self._auth,
        }
        if content_type:
            headers["Content-Type"] = "application/json"
        return headers

    def _request(self, method, path, body=None, raw=False):
        url = "{}/{}".format(self.base.rstrip("/"), path.lstrip("/"))
        data = None
        headers = self._headers(content_type=body is not None and not raw)
        if body is not None:
            if raw:
                data = body if isinstance(body, bytes) else body.encode("utf-8")
                headers["Content-Type"] = "application/x-ndjson"
            else:
                data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = resp.read().decode("utf-8")
                if not payload:
                    return {}
                return json.loads(payload)
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError("ES HTTP {}: {}".format(e.code, detail)) from e

    def search_products(self, index_name, product_ids):
        if not product_ids:
            return {}
        body = {"docs": [{"_id": str(pid), "_source": True} for pid in product_ids]}
        data = self._request("POST", "{}/_mget".format(index_name), body)
        out: dict[str, Any] = {}
        for doc in data.get("docs", []):
            if not doc.get("found"):
                continue
            pid = str(doc.get("_id") or "")
            src = doc.get("_source") or {}
            if pid:
                out[pid] = src
        return out

    def index_exists(self, index_name):
        url = "{}/{}".format(self.base.rstrip("/"), index_name)
        req = urllib.request.Request(
            url, method="HEAD", headers=self._headers(content_type=False)
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return 200 <= resp.status < 300
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return False
            detail = e.read().decode("utf-8", errors="replace")[:300]
            raise RuntimeError("ES HTTP {}: {}".format(e.code, detail)) from e

    def ensure_index(self, index_name, mappings=None, settings=None):
        try:
            if self.index_exists(index_name):
                return True
        except Exception:
            return False
        body = {"settings": dict(settings or DEFAULT_INDEX_SETTINGS)}
        if mappings:
            body["mappings"] = mappings
        try:
            self._request("PUT", index_name, body)
            return True
        except RuntimeError as e:
            if "already exists" in str(e).lower() or "resource_already_exists" in str(e):
                return True
            raise

    def save_products(self, index_name, products):
        """Bulk index/upsert docs. Each product may include ``_id``."""
        if not products:
            return True
        lines = []
        for product in products:
            doc = dict(product)
            doc_id = doc.pop("_id", None)
            meta = {"index": {"_index": index_name}}
            if doc_id is not None:
                meta["index"]["_id"] = str(doc_id)
            lines.append(json.dumps(meta))
            lines.append(json.dumps(doc))
        payload = "\n".join(lines) + "\n"
        self._request("POST", "_bulk", payload, raw=True)
        return True

    def update_docs(self, index_name, doc_ids, update_body):
        """Partial-update many docs with the same update_body (expects ``doc``)."""
        if not doc_ids:
            return True
        lines = []
        for doc_id in doc_ids:
            meta = {"update": {"_index": index_name, "_id": str(doc_id)}}
            lines.append(json.dumps(meta))
            lines.append(json.dumps(update_body))
        payload = "\n".join(lines) + "\n"
        self._request("POST", "_bulk", payload, raw=True)
        return True

    def scan(self, index_name, query=None, size=100):
        """Yield hits ``{_id, _source}`` via scroll."""
        body = {
            "size": size,
            "query": query or {"match_all": {}},
            "sort": ["_doc"],
        }
        data = self._request(
            "POST",
            "{}/_search?scroll=2m".format(index_name),
            body,
        )
        scroll_id = data.get("_scroll_id")
        hits = (data.get("hits") or {}).get("hits") or []
        try:
            while hits:
                for hit in hits:
                    yield {
                        "_id": hit.get("_id"),
                        "_source": hit.get("_source") or {},
                    }
                if not scroll_id:
                    break
                data = self._request(
                    "POST",
                    "_search/scroll",
                    {"scroll": "2m", "scroll_id": scroll_id},
                )
                scroll_id = data.get("_scroll_id")
                hits = (data.get("hits") or {}).get("hits") or []
        finally:
            if scroll_id:
                try:
                    self._request(
                        "DELETE",
                        "_search/scroll",
                        {"scroll_id": [scroll_id]},
                    )
                except Exception:
                    pass
