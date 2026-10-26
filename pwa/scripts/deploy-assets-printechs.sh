#!/usr/bin/env bash
# Interim deploy: works on printechs.com WITHOUT nginx /mobile changes.
# URL: https://printechs.com/assets/erp_analysis/pwa/
set -euo pipefail
BENCH="${BENCH_PATH:-/home/erpnext/frappe-bench}"
ROOT="$BENCH/apps/erp_analysis/pwa"
TARGET="$BENCH/sites/assets/erp_analysis/pwa"

export VITE_BASE="/assets/erp_analysis/pwa/"
export VITE_API_BASE="${VITE_API_BASE:-https://printechs.com}"
export VITE_PILOT_EMAILS="${VITE_PILOT_EMAILS:-sakeer@printechs.com,raheem@printechs.com}"
npm run build --prefix "$ROOT"
mkdir -p "$TARGET"
rsync -a --delete "$ROOT/dist/" "$TARGET/"
# So /assets/erp_analysis/pwa/login/ loads the SPA (nginx serves login/index.html)
mkdir -p "$TARGET/login"
cp "$TARGET/index.html" "$TARGET/login/index.html"
cp "$ROOT/public/login-redirect.html" "$TARGET/login.html"
echo "Live at: https://printechs.com/assets/erp_analysis/pwa/index.html#/login"
echo "Also:     https://printechs.com/assets/erp_analysis/pwa/login/"
