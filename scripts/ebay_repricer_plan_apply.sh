#!/usr/bin/env bash
# DEPRECATED: prefer parallel per-tier plan + separate apply cron.
# See scripts/crontab.ebay_repricer.example and scripts/em_ebay_repricer.vps.sh.
#
# Legacy: plan (cart/ads/catalog sequentially) then apply. One flock for the whole chain.
#
#   ./scripts/ebay_repricer_plan_apply.sh
#   ./scripts/ebay_repricer_plan_apply.sh --limit 100   # forwarded to plan only

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "[ebay_repricer] WARNING: ebay_repricer_plan_apply.sh is deprecated; use plan <tier> + apply" >&2

export PATH="${HOME}/.local/bin:/usr/local/bin:/usr/bin:/bin:${PATH}"
STORE_CODE="${STORE_CODE:-em-spree}"
MARKETPLACE="${MARKETPLACE:-us}"
GCS_SA="${GCS_SERVICE_ACCOUNT_PATH:-${HOME}/.em_celery/gcs-sa.json}"
TIERS="${TIERS:-cart,ads,catalog}"

cd "${ROOT}"
exec "${SCRIPT_DIR}/run_with_lock.sh" ebay_repricer_plan_apply \
  bash -c '
set -euo pipefail
echo "[ebay_repricer] plan start $(date -u +%Y-%m-%dT%H:%M:%SZ)"
uv run em-ebay-repricer-plan \
  -s "$0" \
  -m "$1" \
  --tiers "$2" \
  -g "$3" \
  "${@:4}"
echo "[ebay_repricer] apply start $(date -u +%Y-%m-%dT%H:%M:%SZ)"
uv run em-ebay-repricer-apply \
  -s "$0" \
  -m "$1"
echo "[ebay_repricer] done $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  ' \
  "${STORE_CODE}" \
  "${MARKETPLACE}" \
  "${TIERS}" \
  "${GCS_SA}" \
  "$@"
