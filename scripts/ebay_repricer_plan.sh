#!/usr/bin/env bash
# Plan-only: cart → ads → catalog into ebay_repricer_pending (no Spree).
#
#   ./scripts/ebay_repricer_plan.sh
#   ./scripts/ebay_repricer_plan.sh --limit 50
#   MARKETPLACE=us STORE_CODE=em-spree ./scripts/ebay_repricer_plan.sh

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

export PATH="${HOME}/.local/bin:/usr/local/bin:/usr/bin:/bin:${PATH}"
STORE_CODE="${STORE_CODE:-em-spree}"
MARKETPLACE="${MARKETPLACE:-us}"
GCS_SA="${GCS_SERVICE_ACCOUNT_PATH:-${HOME}/.em_celery/gcs-sa.json}"
TIERS="${TIERS:-cart,ads,catalog}"

cd "${ROOT}"
exec "${SCRIPT_DIR}/run_with_lock.sh" ebay_repricer_plan \
  uv run em-ebay-repricer-plan \
  -s "${STORE_CODE}" \
  -m "${MARKETPLACE}" \
  --tiers "${TIERS}" \
  -g "${GCS_SA}" \
  "$@"
