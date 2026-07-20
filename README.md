# ebay-reprice-export

Export Ebay_US catalog prices/availability from `em-catalog` (`product_sources` + `product_catalogs`) vs calculated offers from ES `ebay_us_products` to CSV. Does **not** write Spree.

## Setup

```bash
uv venv .venv
uv pip install -e .
# Requires ~/.em_celery/config.ini with [pg_db] and [product_service]
```

## Usage

```bash
# smoke
.venv/bin/ebay-reprice-export -m us -t 30 -l 500 -o reports/smoke.csv

# full (~1.26M rows, ~20 min on VPS @ ~1200/s)
.venv/bin/ebay-reprice-export -m us -t 30 -o reports/ebay_us_reprice_export_full.csv
```

## CSV columns

`product_id`, `source_product_id`, `handle`, `variant_id`, `catalog_price`, `catalog_availability`, `ebay_*`, `calculated_price`, `calculated_quantity`, `calculated_availability`, `filter_passed`, `filter_reason`, `expired`
