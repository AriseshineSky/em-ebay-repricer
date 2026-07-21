# -*- coding: utf-8 -*-

import json
from pathlib import Path


class SeedFileDataSource:
    """Read product records from tab-separated GCS seed files.

    Duplicate ``product_id`` or item id (``source_product_id`` / ``ebay_id`` /
    ``id``) rows are skipped on load; first occurrence wins.
    """

    def __init__(self, file_path):
        self.file_path = Path(file_path)

    def iter_products(self, marketplace=None):
        if not self.file_path.is_file():
            return

        seen_product_ids = set()
        seen_source_ids = set()
        with open(self.file_path, encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                if not line.strip():
                    continue
                parts = line.strip().split("\t", 1)
                if len(parts) < 2 or not parts[1].strip():
                    continue
                try:
                    record = json.loads(parts[1].strip())
                except Exception:
                    continue
                if not isinstance(record, dict):
                    yield record
                    continue

                pid = record.get("product_id")
                spid = (
                    record.get("source_product_id")
                    or record.get("ebay_id")
                    or record.get("id")
                )
                if pid not in (None, ""):
                    pid_key = str(pid)
                    if pid_key in seen_product_ids:
                        continue
                else:
                    pid_key = None
                if spid not in (None, ""):
                    spid_key = str(spid).strip()
                    if spid_key in seen_source_ids:
                        continue
                else:
                    spid_key = None

                if pid_key is not None:
                    seen_product_ids.add(pid_key)
                if spid_key is not None:
                    seen_source_ids.add(spid_key)
                yield record
