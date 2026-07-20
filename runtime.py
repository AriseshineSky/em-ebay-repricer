# -*- coding: utf-8 -*-
"""App bootstrap: config and logging."""

from __future__ import annotations

import logging
import os
import sys
from configparser import ConfigParser

ENV = os.getenv("ENV", "prod")
LOG_LEVEL = logging.DEBUG if ENV == "dev" else logging.INFO
logger = logging.getLogger("em_ebay_repricer")
formatter = logging.Formatter("%(asctime)s [%(levelname)s]: %(message)s")
logger.setLevel(LOG_LEVEL)
if not logger.handlers:
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

_cfg = None


def get_config_path(explicit=None):
    if explicit:
        return os.path.abspath(os.path.expanduser(explicit))
    return os.path.abspath(
        os.path.expanduser(
            os.getenv(
                "EM_EBAY_REPRICER_CONFIG",
                os.path.join("~", ".em_ebay_repricer", "config.ini"),
            )
        )
    )


def get_config(path=None):
    global _cfg
    if _cfg is not None and path is None:
        return _cfg
    config_path = get_config_path(path)
    if not os.path.isfile(config_path):
        # Fallbacks for local/dev
        for candidate in ("./config.ini", os.path.expanduser("~/.em_celery/config.ini")):
            if os.path.isfile(candidate):
                config_path = os.path.abspath(candidate)
                break
        else:
            raise ValueError("Could not find configuration file - {}".format(config_path))
    cp = ConfigParser(interpolation=None)
    cp.read(config_path)
    loaded = {section: dict(cp.items(section)) for section in cp.sections()}
    if path is None:
        _cfg = loaded
    return loaded
