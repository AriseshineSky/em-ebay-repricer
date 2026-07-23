#!/usr/bin/env bash
# Apply pending Ebay prices from ES to Spree set_offers.
#
#   ./scripts/ebay_repricer_apply.sh
#   ./scripts/ebay_repricer_apply.sh --dry-run --limit 20

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

export PATH="${HOME}/.local/bin:/usr/local/bin:/usr/bin:/bin:${PATH}"
STORE_CODE="${STORE_CODE:-em-spree}"
MARKETPLACE="${MARKETPLACE:-us}"

cd "${ROOT}"
exec "${SCRIPT_DIR}/run_with_lock.sh" ebay_repricer_apply \
  uv run em-ebay-repricer-apply \
  -s "${STORE_CODE}" \
  -m "${MARKETPLACE}" \
  "$@"
