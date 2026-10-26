# PWA Phase 2a — Printechs Business Insight (Web)

**URL (target):** `https://printechs.com/mobile/`  
**URL (works today, no nginx change):** `https://printechs.com/assets/erp_analysis/pwa/`  
**OAuth redirect:** `https://printechs.com/mobile/oauth`  
**Pilot user:** `sakeer@printechs.com`  
**Auth:** Same OAuth password grant + Bearer APIs as native mobile.

---

## What’s included (2a)

- Login (ERPNext email + password)
- Pilot gate (`VITE_PILOT_EMAILS`)
- Home dashboard (`dashboard_id=home`) — KPI grid, period + territory filters, refresh
- Sales board stub (`/mobile/board/sales_overview`) — KPIs only
- OAuth callback route (for future auth-code flow)

---

## Backend one-time (production)

```bash
bench --site printechs.com execute erp_analysis.oauth_setup.ensure_oauth_client
bench --site printechs.com clear-cache
```

This registers redirect URIs including `https://printechs.com/mobile/oauth`.

---

## Local development

```bash
cd apps/erp_analysis/pwa
cp .env.example .env
npm install
npm run dev
```

Open `http://localhost:5173/mobile/` (Vite proxies `/api` to `site1.local` by default).

Override proxy target:

```bash
VITE_DEV_PROXY=http://site1.local npm run dev
```

Or set `VITE_API_BASE=http://site1.local` in `.env` (disables need for proxy on API host).

---

## Production build

```bash
cd apps/erp_analysis/pwa
npm ci
npm run build
```

Output: `pwa/dist/` (assets prefixed with `/mobile/`).

### Nginx (example)

```nginx
location /mobile {
    alias /var/www/printechs/mobile;
    try_files $uri $uri/ /mobile/index.html;
}
```

Deploy by copying `dist/*` to `/var/www/printechs/mobile/`.

Same-origin `https://printechs.com` → no CORS changes needed.

---

## Environment (build-time)

| Variable | Example | Purpose |
|----------|---------|---------|
| `VITE_API_BASE` | *(empty)* | API origin; empty = same as PWA host |
| `VITE_PILOT_EMAILS` | `sakeer@printechs.com` | Comma-separated pilot users |

---

## API flow (same as mobile)

1. `GET/POST erp_analysis.config.get_client_id` (guest)
2. `POST frappe.integrations.oauth2.get_token` (password grant)
3. `erp_analysis.api.get_my_access`
4. `erp_analysis.api.get_mobile_bootstrap`
5. `erp_analysis.api.get_dashboard_board_data`

---

## Why `/mobile/` may 404 on printechs.com

The marketing site (Next.js on port 3000) owns `location /` on `printechs.com`.  
`/mobile` is **not** ERPNext — nginx must serve static files **before** the Next proxy.

**Fix (one-time, sudo):**

```bash
sudo bash apps/erp_analysis/pwa/scripts/install-nginx-mobile.sh
./apps/erp_analysis/pwa/scripts/deploy-staging-site1.sh
```

**Interim (already works):**

```bash
./apps/erp_analysis/pwa/scripts/deploy-assets-printechs.sh
```

Open: **https://printechs.com/assets/erp_analysis/pwa/index.html**  
(Routes use hash URLs, e.g. `#/login`, so deep links work without extra nginx.)

---

## Staging on `site1.local`

```bash
./apps/erp_analysis/pwa/scripts/deploy-staging-site1.sh
```

Serves static files from `sites/site1.local/public/mobile/` → **`http://site1.local/mobile/`** (same host as ERPNext API).

Pilot login: `sakeer@printechs.com` with ERPNext password.

## Sales / Receivables / Inventory boards (2a+)

Board routes render:

- **KPI** grid
- **LINE / BAR / PIE / DONUT** — horizontal bar list from `chart.series`
- **RANKING / TABLE / LIST** — top rows from `table.rows` or `series`

## Phase 2b (next)

- PWA service worker + icons (`public/icons/`)
- Richer charts (optional chart library)
- Install prompt UX
- Production deploy to `printechs.com/mobile` via `scripts/deploy-dist.sh`
