#!/usr/bin/env bash
# Staging deploy for site1.local → https://printechs.com/mobile/
set -euo pipefail
BENCH="${BENCH_PATH:-/home/erpnext/frappe-bench}"
ROOT="$BENCH/apps/erp_analysis/pwa"
TARGET="$BENCH/sites/site1.local/public/mobile"

export VITE_BASE="/mobile/"
export VITE_API_BASE="${VITE_API_BASE:-https://printechs.com}"
export VITE_PILOT_EMAILS="${VITE_PILOT_EMAILS:-sakeer@printechs.com,raheem@printechs.com}"
npm run build --prefix "$ROOT"
mkdir -p "$TARGET"
rsync -a --delete "$ROOT/dist/" "$TARGET/"
mkdir -p "$TARGET/login"
cp "$TARGET/index.html" "$TARGET/login/index.html"
cp "$ROOT/public/login-redirect.html" "$TARGET/login.html"
echo "Staging PWA: $TARGET"
echo "Open: https://printechs.com/mobile/#/login (after: sudo nginx -t && sudo systemctl reload nginx)"
