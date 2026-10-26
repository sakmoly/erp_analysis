#!/usr/bin/env bash
# Permanent URL: https://printechs.com/mobile/
# Requires sudo — inserts PWA location before Next.js catch-all in frappe-bench.conf
set -euo pipefail
CONF="/etc/nginx/conf.d/frappe-bench.conf"
SNIPPET="$(dirname "$0")/../nginx/mobile-pwa-snippet.conf"
MARKER="# Business Insight PWA"

if grep -q "$MARKER" "$CONF" 2>/dev/null; then
  echo "Nginx mobile block already present in $CONF"
  exit 0
fi

if ! sudo test -w "$CONF"; then
  echo "Run with sudo or add snippet manually from: $SNIPPET"
  exit 1
fi

sudo cp "$CONF" "${CONF}.bak.$(date +%Y%m%d%H%M%S)"
sudo sed -i "/location \\/ {/i\\
\\t$MARKER (static build under site public/mobile)\\
\\tlocation = /mobile {\\
\\t\\treturn 301 /mobile/;\\
\\t}\\
\\
\\tlocation ^~ /mobile/ {\\
\\t\\talias /home/erpnext/frappe-bench/sites/site1.local/public/mobile/;\\
\\t\\tindex index.html;\\
\\t\\tadd_header Cache-Control \"no-cache\";\\
\\t}\\
" "$CONF"

sudo nginx -t && sudo systemctl reload nginx
echo "Done. Deploy static files: ./deploy-staging-site1.sh"
echo "Open: https://printechs.com/mobile/"
