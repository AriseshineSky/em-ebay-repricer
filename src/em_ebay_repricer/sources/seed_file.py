# -*- coding: utf-8 -*-

import json
from pathlib import Path


class SeedFileDataSource:
    """Read product records from tab-separated GCS seed files."""

    def __init__(self, file_path):
        self.file_path = Path(file_path)

    def iter_products(self, marketplace=None):
        if not self.file_path.is_file():
            return

        with open(self.file_path, encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                if not line.strip():
                    continue
                parts = line.strip().split("\t", 1)
                if len(parts) < 2 or not parts[1].strip():
                    continue
                try:
                    yield json.loads(parts[1].strip())
                except Exception:
                    continue
