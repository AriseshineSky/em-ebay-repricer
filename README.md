# ebay-reprice-export

Standalone tool that compares **catalog** (Postgres `product_sources` + `product_catalogs`) with **calculated** Ebay offers from Elasticsearch (`ebay_{marketplace}_products`) and writes an audit CSV.

It does **not** update any store / Spree inventory.

## Requirements

- Python 3.12+
- Postgres catalog DB with `product_sources` and `product_catalogs`
- Elasticsearch index such as `ebay_us_products` (document `_id` = Ebay item id)

## Setup

```bash
cp config.example.ini config.ini
# edit config.ini with your Postgres + Elasticsearch credentials

uv venv .venv
uv pip install -e .
# or: pip install -e .
```

## Usage

```bash
# smoke test
ebay-reprice-export -m us -t 30 -l 500 -o reports/smoke.csv --config config.ini

# full export
ebay-reprice-export -m us -t 30 -o reports/ebay_us_reprice_export_full.csv --config config.ini
```

Environment alternatives:

- `EBAY_REPRICE_CONFIG=/path/to/config.ini`
- `CATALOG_DATABASE_URL=postgresql://...` (overrides `[pg_db]` DSN pieces)

## CSV columns

| Column | Source |
|--------|--------|
| `product_id`, `source_product_id`, `handle`, `variant_id` | Postgres |
| `catalog_price`, `catalog_availability` | `product_catalogs` (current site) |
| `ebay_price`, `ebay_shipping_fee`, `ebay_available_qty`, `ebay_existence`, `ebay_date` | Elasticsearch |
| `calculated_price`, `calculated_quantity`, `calculated_availability` | filter + price calculator |
| `filter_passed`, `filter_reason`, `expired` | diagnostics |

## License

MIT
