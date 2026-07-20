# -*- coding: utf-8 -*-

from __future__ import annotations

import configparser
import os
from pathlib import Path


def load_em_celery_config(path=None):
  if path is None:
    path = os.getenv(
      "MWS_COLLECTOR_CONFIGURATION_PATH",
      os.path.expanduser("~/.em_celery/config.ini"),
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
