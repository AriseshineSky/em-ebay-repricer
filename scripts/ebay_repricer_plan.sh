#!/usr/bin/env bash
# Plan one tier into ebay_repricer_pending (no Spree). Per-tier flock.
#
#   ./scripts/ebay_repricer_plan.sh cart
#   ./scripts/ebay_repricer_plan.sh ads --limit 50
#   MARKETPLACE=us STORE_CODE=em-spree ./scripts/ebay_repricer_plan.sh catalog

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

TIER="${1:-}"
if [[ -z "${TIER}" ]]; then
  echo "Usage: $0 <cart|ads|catalog> [extra em-ebay-repricer-plan args...]" >&2
  exit 2
fi
shift

case "${TIER}" in
  cart|ads|catalog) ;;
  *)
    echo "Unknown tier: ${TIER} (expected cart|ads|catalog)" >&2
    exit 2
    ;;
esac

export PATH="${HOME}/.local/bin:/usr/local/bin:/usr/bin:/bin:${PATH}"
STORE_CODE="${STORE_CODE:-em-spree}"
MARKETPLACE="${MARKETPLACE:-us}"
GCS_SA="${GCS_SERVICE_ACCOUNT_PATH:-${HOME}/.em_celery/gcs-sa.json}"

cd "${ROOT}"
exec "${SCRIPT_DIR}/run_with_lock.sh" "ebay_repricer_plan_${TIER}" \
  uv run em-ebay-repricer-plan \
  -s "${STORE_CODE}" \
  -m "${MARKETPLACE}" \
  --tiers "${TIER}" \
  -g "${GCS_SA}" \
  "$@"
