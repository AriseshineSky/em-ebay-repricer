# -*- coding: utf-8 -*-

from __future__ import annotations

import configparser
import os
from pathlib import Path


def load_config(path=None):
  """Load INI config. Prefer --config / EBAY_REPRICE_CONFIG / ./config.ini."""
  if path is None:
    path = os.getenv("EBAY_REPRICE_CONFIG")
  if path is None:
    for candidate in ("./config.ini", os.path.expanduser("~/.ebay_reprice_export/config.ini")):
      if Path(candidate).is_file():
        path = candidate
        break
  if path is None:
    raise FileNotFoundError(
      "config not found. Copy config.example.ini to config.ini "
      "or pass --config / set EBAY_REPRICE_CONFIG."
    )

  path = os.path.expanduser(path)
  if not Path(path).is_file():
    raise FileNotFoundError("config not found: {}".format(path))

  parser = configparser.ConfigParser()
  parser.read(path)
  cfg = {}
  for section in parser.sections():
    cfg[section] = dict(parser.items(section))
  return cfg


# Backward-compatible alias
load_em_celery_config = load_config
