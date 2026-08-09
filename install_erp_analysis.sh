#!/usr/bin/env bash
# Install erp_analysis on a Frappe/ERPNext bench (see ERP_ANALYSIS_API_CONTRACT.md)
set -euo pipefail

SITE="${SITE:-site1.local}"
BENCH_PATH="${BENCH_PATH:-$HOME/frappe-bench}"

cd "$BENCH_PATH"

if [ ! -d apps/erp_analysis ]; then
  echo "ERROR: apps/erp_analysis missing. Clone/copy the app first." >&2
  exit 1
fi

grep -qx 'erp_analysis' sites/apps.txt || echo 'erp_analysis' >> sites/apps.txt
./env/bin/pip install -e apps/erp_analysis

bench --site "$SITE" install-app erp_analysis || true
bench --site "$SITE" migrate
bench --site "$SITE" execute erp_analysis.oauth_setup.ensure_oauth_client
bench --site "$SITE" clear-cache

echo
echo "Verify:"
echo "  curl -s \"https://<your-host>/api/method/erp_analysis.api.health\""
echo "  curl -s \"https://<your-host>/api/method/erp_analysis.config.get_client_id\""
