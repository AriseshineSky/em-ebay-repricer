# -*- coding: utf-8 -*-

from __future__ import annotations

import datetime
import logging
import os
import sys

import click

from .config import load_em_celery_config
from .es_client import EsProductClient
from .exporter import EbayRepricerExporter
from .price_calculator import PriceCalculator


def _setup_logging():
  logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s]: %(message)s",
    stream=sys.stdout,
  )


@click.command("ebay-reprice-export")
@click.option("-m", "--marketplace", type=str, default="us")
@click.option("-t", "--ttl", type=int, default=30)
@click.option("-o", "--output", type=str, default=None)
@click.option("-l", "--limit", type=int, default=0, help="0 = all")
@click.option("--batch-size", type=int, default=250)
@click.option("--config", "config_path", type=str, default=None)
def main(marketplace, ttl, output, limit, batch_size, config_path):
  """Export catalog vs calculated Ebay offers to CSV (no Spree writes)."""
  _setup_logging()
  marketplace = marketplace.lower()
  cfg = load_em_celery_config(config_path)

  pg_config = cfg.get("pg_db")
  if not pg_config:
    raise click.ClickException("Missing [pg_db] in config.ini")

  product_cfg = cfg.get("product_service")
  if not product_cfg:
    raise click.ClickException("Missing [product_service] in config.ini")

  price_rules = {"roi": 0.3, "ad_cost": 5, "transfer_cost": 1}
  price_rules_cfg = cfg.get("price.rules.ebay_{}".format(marketplace), {}) or {}
  for k, v in price_rules_cfg.items():
    try:
      price_rules[k] = round(float(v), 2)
    except (TypeError, ValueError):
      pass

  if not output:
    output = "/tmp/ebay_{}_reprice_export_{}.csv".format(
      marketplace, datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    )
  output = os.path.abspath(os.path.expanduser(output))

  product_service = EsProductClient(
    product_cfg["host"],
    product_cfg.get("port", "80"),
    product_cfg["user"],
    product_cfg["password"],
  )
  price_calculator = PriceCalculator(price_rules)

  exporter = EbayRepricerExporter(
    product_service=product_service,
    price_calculator=price_calculator,
    marketplace=marketplace,
    ttl=ttl,
    output_path=output,
    pg_config=pg_config,
    limit=limit,
    batch_size=batch_size,
  )
  stats = exporter.run()
  click.echo("Wrote {} (exported={})".format(output, stats.get("exported_cnt")))


if __name__ == "__main__":
  main()
