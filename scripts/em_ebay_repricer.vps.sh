#!/usr/bin/env bash
# VPS cron entry for em-ebay-repricer (install as /home/Admin/scripts/em_ebay_repricer.sh).
# Per-tier plan flock; apply is independent.
#
# Plan (calc → ES pending, no Spree):
#   /home/Admin/scripts/em_ebay_repricer.sh plan cart|ads|catalog
#
# Apply pending/failed → Spree:
#   /home/Admin/scripts/em_ebay_repricer.sh apply
#
# Extra args are forwarded (e.g. --dry-run --limit 5).

set -euo pipefail

usage() {
  echo "Usage: $0 plan <cart|ads|catalog> [extra args...]" >&2
  echo "   or: $0 apply [extra args...]" >&2
  exit 2
}

MODE="${1:-}"
if [[ -z "${MODE}" ]]; then
  usage
fi
shift

export PATH="${HOME}/.local/bin:/usr/local/bin:/usr/bin:/bin:${PATH}"
PROJECT_ROOT="${EM_EBAY_REPRICER_ROOT:-${HOME}/src/em-ebay-repricer}"
cd "${PROJECT_ROOT}"

case "${MODE}" in
  plan)
    TIER="${1:-}"
    if [[ -z "${TIER}" ]]; then
      usage
    fi
    shift
    exec ./scripts/ebay_repricer_plan.sh "${TIER}" "$@"
    ;;
  apply)
    exec ./scripts/ebay_repricer_apply.sh "$@"
    ;;
  plan-apply)
    echo "Deprecated: use separate 'plan <tier>' and 'apply' cron entries." >&2
    echo "See scripts/crontab.ebay_repricer.example" >&2
    exit 2
    ;;
  *)
    usage
    ;;
esac
