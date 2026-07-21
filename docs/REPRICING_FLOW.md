# em-ebay-repricer plan / apply flow

Standalone Ebay Spree repricer with **plan → apply** split.

## Commands

| Command | Spree? | Writes |
|---------|--------|--------|
| `em-ebay-repricer-plan` | No | `ebay_repricer_pending` + `ebay_repricer_metrics` |
| `em-ebay-repricer-apply` | Yes | `set_offers`; marks pending `applied`/`failed` |
| `em-ebay-repricer` | Yes (live) | pending state + immediate `set_offers` |

## Data sources (tiers)

| Tier | Source |
|------|--------|
| cart | GCS `em-analytics/carts/sources/EBAY_{MP}.txt` |
| ads | GCS `em-analytics/sources/EBAY_{MP}.txt` |
| catalog | PG `product_sources` + `product_catalogs` (skip discontinued) |

Order: `cart → ads → catalog`.

## Indexes

| Index | Role |
|-------|------|
| `ebay_{mp}_products` | **Read-only** source crawl docs (`_id` = Ebay item id) |
| `ebay_repricer_pending` | Plan state: `calc_at`, `tier_*`, offer, status |
| `ebay_repricer_metrics` | Per-run metrics for monitoring-dashboard |

Pending `_id`: `{store_code}_{marketplace}_{product_id}`.

### Pending fields

- `status`: `pending` / `skipped_price` / `skipped_fresh` / `filtered` / `applied` / `failed`
- `calc_at`: last real recalculation time (freshness anchor)
- `source_updated_at`: source doc `date`/`time` at calc
- `tier_cart` / `tier_ads` / `tier_catalog`: cumulative tier markers
- `old_price`: store catalog price at plan time
- `offer` / `variants` / `handle` / `ebay_id`

## Decision rules

```text
1) Freshness: recalculate only if source date/time > pending.calc_at
   (or no calc_at / --force). Else skipped_fresh (+ optional tier_* patch).

2) Filter / missing ES → status=filtered, offer price/qty 0, still upsert calc_at.

3) Price diff: |new_price - catalog_price| < threshold → skipped_price
   (default $1, --price-diff-threshold or [ebay_repricer] price_diff_threshold).

4) Else status=pending → apply (or live set_offers).
```

## Price formula

Source cost = ES `price` + `shipping_fee` (FX to USD as needed).  
`PriceCalculator` takes max of min-profit path, margin path, and product-cost-rate path  
(defaults / `[price.rules.ebay_{mp}]`: roi, ad_cost, transfer_cost, …).

## Monitoring

Dashboard reads `ebay_repricer_metrics` (`source` = `ebay_repricer` / `ebay_repricer_plan`,  
`metric_kind` = `final` / `plan`). Env: `ES_EBAY_REPRICER_METRICS_INDEXES`.

## Examples

```bash
em-ebay-repricer-plan -s em-spree -m us --tiers cart --limit 50
em-ebay-repricer-plan -s em-spree -m us --tiers cart --limit 50   # mostly skipped_fresh
em-ebay-repricer-apply -s em-spree -m us --dry-run
em-ebay-repricer-apply -s em-spree -m us
```
