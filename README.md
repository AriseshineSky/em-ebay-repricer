# em-ebay-repricer

Standalone **Ebay Spree repricer**: read product IDs from **cart / ads / catalog**, load Ebay offers from Elasticsearch, calculate prices into **`ebay_repricer_pending`**, then apply Spree `set_offers`.

See [docs/REPRICING_FLOW.md](docs/REPRICING_FLOW.md) for plan/apply, freshness, and tier markers.

Mirrors the [em-amz-repricer](https://github.com/AriseshineSky) three-tier pattern. Does **not** enqueue crawler Redis URLs (that is offers-update, not reprice).

## Data sources

| Tier | Source |
|------|--------|
| cart | `gs://em-bucket/em-analytics/carts/sources/EBAY_{MP}.txt` |
| ads | `gs://em-bucket/em-analytics/sources/EBAY_{MP}.txt` |
| catalog | Postgres `product_sources` (`Ebay_{MP}`) + `product_catalogs` |

ES index: `ebay_{marketplace}_products` (document `_id` = Ebay item id).

## Setup

```bash
cp config.example.ini ~/.em_ebay_repricer/config.ini
# fill PG, ES, and Spree credentials
# place GCS service account at ~/.em_ebay_repricer/gcs-sa.json (for cart/ads)

uv venv .venv
uv pip install -e .
```

## Usage

```bash
# plan (write pending only)
em-ebay-repricer-plan -s em-spree -m us --tiers catalog --limit 100

# apply pending → Spree
em-ebay-repricer-apply -s em-spree -m us --dry-run
em-ebay-repricer-apply -s em-spree -m us

# live (calc + set_offers in one process)
em-ebay-repricer -s em-spree -m us --tiers cart,ads,catalog \
  -g ~/.em_ebay_repricer/gcs-sa.json
```

Config path: `EM_EBAY_REPRICER_CONFIG` or `~/.em_ebay_repricer/config.ini` or `./config.ini`.

## License

MIT
