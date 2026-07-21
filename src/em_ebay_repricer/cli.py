# -*- coding: utf-8 -*-

from __future__ import annotations

import click

from em_ebay_repricer.cli_common import run_reprice_command
from em_ebay_repricer.repricer import EbayRepricer


@click.command("em-ebay-repricer")
@click.option("-s", "--store_code", required=True, type=str)
@click.option(
    "-g",
    "--gcs_service_account_path",
    type=str,
    default="~/.em_celery/gcs-sa.json",
    show_default=True,
)
@click.option("-m", "--marketplace", type=str, default="us", show_default=True)
@click.option("-t", "--ttl", type=int, default=30, show_default=True)
@click.option("--tiers", "tiers_arg", multiple=True, help="cart, ads, catalog")
@click.option("--dry-run", is_flag=True)
@click.option("--force", is_flag=True, help="Ignore freshness and price-diff skips.")
@click.option(
    "--price-diff-threshold",
    type=float,
    default=None,
    help="Skip set_offers when |delta| < threshold (default config or 1.0).",
)
@click.option("--limit", type=int, default=0)
@click.option("--batch-size", type=int, default=250, show_default=True)
@click.option("--config", "config_path", type=str, default=None)
def reprice(
    store_code,
    gcs_service_account_path,
    marketplace,
    ttl,
    tiers_arg,
    dry_run,
    force,
    price_diff_threshold,
    limit,
    batch_size,
    config_path,
):
    """Live reprice: calculate, write pending state, and call Spree set_offers."""
    run_reprice_command(
        store_code=store_code,
        gcs_service_account_path=gcs_service_account_path,
        marketplace=marketplace,
        ttl=ttl,
        tiers_arg=tiers_arg,
        dry_run=dry_run,
        limit=limit,
        batch_size=batch_size,
        config_path=config_path,
        mode=EbayRepricer.MODE_LIVE,
        force=force,
        price_diff_threshold=price_diff_threshold,
        plan=False,
    )


if __name__ == "__main__":
    reprice()
