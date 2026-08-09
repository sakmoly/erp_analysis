# erp_analysis — Server Setup + Mobile API Contract (v1)

Installable Frappe app for **any ERPNext site**. The Printechs mobile app talks to these methods when a real server URL is saved.

**Mobile defaults**

- Empty server URL → **Demo mode** (mock data; any email + any 6-digit OTP).
- Saving a real URL → demo off; password login; health check against `erp_analysis.api.health`.

---

## Quick start (run on the ERPNext server)

Copy [`docs/erp_analysis/install_erp_analysis.sh`](./erp_analysis/install_erp_analysis.sh) to your bench host, then:

```bash
# From this repo (example: scp to server)
# scp docs/erp_analysis/install_erp_analysis.sh user@server:~/install_erp_analysis.sh

# On the server:
chmod +x ~/install_erp_analysis.sh

# SITE = your site name, e.g. erp.example.com
export SITE="site1.local"
export BENCH_PATH="$HOME/frappe-bench"   # change if needed

# Optional: if printechs_utility already exists on this site, generate wrappers
# export MIGRATE_FROM_PRINTECHS=1

~/install_erp_analysis.sh
```

What the script does:

1. Creates app **`erp_analysis`** under `apps/` (if missing)
2. Writes whitelisted **stub APIs** matching this contract (health, config, BA modules)
3. `bench get-app` path / links app into the bench
4. `bench --site $SITE install-app erp_analysis`
5. `bench --site $SITE migrate`
6. Creates / updates an **OAuth Client** with Password grant for mobile login
7. Prints the **client_id** to paste into the mobile app (or returned by `get_client_id`)
8. Restarts bench processes

Then on the phone: Server settings → your site URL → Login with ERPNext user + password.

---

## Prerequisites

- Frappe / ERPNext bench already working
- SSH access to the bench server
- Site name known (`bench --site <site> list-apps`)
- Bench user permissions to create apps and migrate

```bash
# Confirm site
cd ~/frappe-bench
bench --site site1.local list-apps
```

---

## Manual install (if you prefer step-by-step)

### 1. Create the app

```bash
cd ~/frappe-bench
bench new-app erp_analysis
# App Title: ERP Analysis
# App Description: Mobile Business Analysis APIs for ERPNext
# App Publisher: Printechs
# App Email: support@printechs.com
# App License: MIT
```

Or use the script (non-interactive scaffold).

### 2. Install on site + migrate

```bash
bench --site site1.local install-app erp_analysis
bench --site site1.local migrate
bench restart
```

### 3. OAuth Client (password login for mobile)

Desk → **OAuth Client** → New:

| Field                | Value                                                      |
| -------------------- | ---------------------------------------------------------- |
| App Name             | Printechs Mobile                                           |
| Grant Type           | **Password** (and Refresh Token if available)              |
| Default Redirect URI | `erpnext://oauth` (placeholder is fine for password grant) |
| Skip Authorization   | optional                                                   |

Copy **Client ID** into the mobile Server Configuration screen,  
or ensure `erp_analysis.config.get_client_id` returns it.

CLI helper (also run by the install script):

```bash
bench --site site1.local execute erp_analysis.oauth_setup.ensure_oauth_client
```

### 4. Verify

```bash
# Health (no auth)
curl -s "https://site1.local/api/method/erp_analysis.api.health"

# Expect: {"message":{"ok":true,"status":"ok","version":"1.0.0"}}
```

Password token (mobile uses this):

```bash
curl -s -X POST "https://site1.local/api/method/frappe.integrations.oauth2.get_token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=password&username=USER&password=PASS&client_id=YOUR_CLIENT_ID"
```

---

## Migrating from `printechs_utility`

If this site already has `printechs_utility`:

1. Install `erp_analysis` (script above).
2. Prefer **thin wrappers** in `erp_analysis` that call existing `printechs_utility` functions (fast cutover).
3. Point the mobile app at `erp_analysis.*` (already done in this repo).
4. After parity is confirmed, move logic into `erp_analysis` and deprecate `printechs_utility`.

Wrapper pattern:

```python
# erp_analysis/dashboard.py
import frappe

@frappe.whitelist()
def get_complete_dashboard_data(**kwargs):
    # Temporary: reuse old implementation
    from printechs_utility.dashboard import get_complete_dashboard_data as _impl
    return _impl(**kwargs)
```

The install script can set `MIGRATE_FROM_PRINTECHS=1` to generate wrappers instead of empty stubs:

```bash
export SITE="site1.local"
export MIGRATE_FROM_PRINTECHS=1
./install_erp_analysis.sh
```

---

## API contract

### Health & config

| Method                               | HTTP | Auth                        | Purpose                                  |
| ------------------------------------ | ---- | --------------------------- | ---------------------------------------- |
| `erp_analysis.api.health`            | GET  | public (`allow_guest=True`) | `{ ok, status, version, message? }`      |
| `erp_analysis.api.get_mobile_config` | GET  | Bearer                      | Modules + server-driven dashboards       |
| `erp_analysis.config.get_client_id`  | GET  | public                      | `{ client_id }` for OAuth password grant |

### `get_mobile_config` response

```json
{
  "app": "erp_analysis",
  "version": "1.0.0",
  "modules": {
    "sales": true,
    "receivables": true,
    "inventory": true,
    "approvals": true,
    "catalogue": false,
    "push": false,
    "settings": true
  },
  "dimensions": {
    "company": true,
    "territory": true,
    "warehouse": true,
    "brand": true,
    "division": true,
    "department": true,
    "cost_center": false,
    "branch": true
  },
  "apis": {},
  "dashboards": [
    {
      "id": "home",
      "title": "Dashboard",
      "module": "sales",
      "widgets": [
        {
          "id": "sales_card",
          "type": "expandable",
          "title": "Sales Performance"
        },
        {
          "id": "receivables_card",
          "type": "expandable",
          "title": "Receivables"
        },
        { "id": "inventory_card", "type": "expandable", "title": "Inventory" }
      ]
    }
  ]
}
```

**Multi-client rules**

| Mechanism | Purpose |
| --------- | ------- |
| `modules.* = false` | Hide whole module (tabs / cards) |
| `dimensions.* = false` | Do not send that filter param; hide related charts (Division, Territory, Department, …) |
| `apis.<method> = false` | Skip that method; mobile returns empty defaults (no crash) |
| Empty arrays / null fields | Always OK — mobile soft-parses and hides empty sections |
| Unexpected kwargs on server | Wrappers must strip `cmd` and filter by Python signature (`fix_cmd_kwargs.sh`) |

Example for a site without Division / Department:

```json
"dimensions": {
  "division": false,
  "department": false
}
```

Widget `type` values (mobile v1): `kpi` | `chart` | `table` | `expandable`.

### Access scope — view vs approve territories

#### Company-wide view overrides (Access Profile checkboxes)

These **override View Territories** for the named module only. Approvals always stay on `approve_territories`.

| Access Profile field | Effect when checked |
| -------------------- | ------------------- |
| `allow_view_all_sales` | Sales / GP / executive sales / sales orders → company-wide |
| `allow_view_all_stock` | Inventory / stock → all warehouses |
| `allow_all_receivable` | Receivables APIs → company-wide AR |

Returned on `get_my_access.scope` with the same names (booleans).

Managers often need **broad Sales visibility** but **narrow Approvals rights**.

Example — user `sakeer@printechs.com`:

| Capability | Territories |
| ---------- | ----------- |
| Sales / GP / analytics (read) | Riyadh, Jeddah, Dammam |
| Approvals inbox + approve/reject | Dammam only |

#### `get_my_access` scope (required shape)

```json
{
  "scope": {
    "user": "sakeer@printechs.com",
    "company": "Printechs Advanced Printing Trading Co.",
    "branch": "Dammam",
    "territory": "Riyadh",
    "territories": ["Riyadh", "Jeddah", "Dammam"],
    "view_territories": ["Riyadh", "Jeddah", "Dammam"],
    "approve_territories": ["Dammam"]
  },
  "profiles": []
}
```

| Field | Meaning |
| ----- | ------- |
| `view_territories` | Read scope for executive / sales / GP / analytics |
| `territories` | Alias of `view_territories` (backward compatible) |
| `approve_territories` | Approvals list + approve/reject only |
| `branch` | Legacy single-site default; mobile uses as **approve** fallback when `approve_territories` is omitted |
| `territory` | Optional primary / home territory |

**Mobile behaviour**

- Executive / Sales: sends `territories=<view_territories csv>`
- Approvals: sends `territories=<approve_territories csv>` (never the full view list)
- Until BA ships `approve_territories`, mobile falls back to **`branch` only** for approvals (so Dammam branch ≠ accidental company-wide approve)

#### BA method rules

| Method | Territory param | Rule |
| ------ | --------------- | ---- |
| `executive.get_executive_dashboard` | `territories` (view) | Sum Sales/GP across listed territories. **Do not** silently restrict to Employee.branch when `territories` is sent |
| `sales_kpis.*` / analytics | `territories` (view) | Same as executive |
| `approvals.get_all_approvals` | `territories` (approve) | Return only docs in those territories |
| `approvals.approve_document` / `reject_document` | — | **Re-check** doc territory ∈ user’s `approve_territories` server-side (never trust client alone) |

#### ERPNext Desk (same policy)

Keep Desk aligned so mobile and Desk never disagree:

1. **View (Sales reports / dashboards):** User Permission or role that allows reading Sales Invoice / reports for all `view_territories` (or company-wide read + BA filters by `view_territories`).
2. **Approve (Workflow):** Only allow apply/approve actions for docs whose Territory (or Branch) is in `approve_territories` — e.g. Workflow condition / custom permission query / server script on `before_transition`.
3. Prefer storing the split on a custom User/Employee field or Role Profile that `get_my_access` reads, rather than hardcoding emails in Python.

### Phase 3A — Executive Dashboard

| Method | HTTP | Auth | Purpose |
| ------ | ---- | ---- | ------- |
| `erp_analysis.executive.get_executive_dashboard` | GET | Bearer | Home Executive 2.0 (preferred) |
| `erp_analysis.dashboard.get_executive_dashboard` | GET | Bearer | Alternate path (mobile tries both) |

**Params:** `company?`, `from_date?`, `to_date?`, `period?` (today|mtd|ytd|…), `territories?` (comma-separated **view** territories), `territory?` (single, legacy)

**Suggested `message` payload** (sections may be null/omitted; no targets / cash):

```json
{
  "meta": {
    "currency": "SAR",
    "company": "Printechs",
    "from_date": "2026-08-01",
    "to_date": "2026-08-05",
    "generated_at": "2026-08-05T12:00:00Z"
  },
  "sales": {
    "today": { "value": 0, "previous": 0, "change_pct": 0 },
    "mtd": { "value": 0, "previous": 0, "change_pct": 0 },
    "ytd": { "value": 0, "previous": 0, "change_pct": 0 }
  },
  "gross_profit": {
    "mtd": { "value": 0, "change_pct": 0 },
    "ytd": { "value": 0, "change_pct": 0 },
    "gp_pct": { "value": 0, "previous": 0, "change_pct": 0 }
  },
  "collection": {
    "today": { "value": 0 },
    "mtd": { "value": 0 },
    "ytd": { "value": 0 }
  },
  "receivables": {
    "total": 0,
    "overdue": 0,
    "overdue_pct": 0,
    "current": 0
  },
  "inventory": {
    "value": 0,
    "low_stock_count": 0,
    "non_moving_value": 0
  },
  "orders": {
    "open_so_value": 0,
    "pending_delivery_value": 0
  },
  "purchasing": {
    "open_po_value": 0,
    "pending_receipt_value": 0
  },
  "payables": {
    "total": 0,
    "overdue": 0
  },
  "approvals": {
    "pending_count": 0
  }
}
```

Mobile normalizes alternate keys (`change_percentage`, `totalUnpaid`, etc.). Enable via `modules.executive` (default true). See `docs/PHASE3_SCOPE.md` (targets & cash deferred).

### Phase 3B′ — Salesperson & Product (no targets)

| Method | Purpose |
| ------ | ------- |
| `erp_analysis.sales.get_salesperson_performance` | Ranking + optional nested customers/invoices/items |
| `erp_analysis.sales.get_product_performance` | Hierarchy `level`: division → brand → item_group → item |

**Params (common):** `company?`, `from_date?`, `to_date?`, `period?`, dimension filters.

**Mobile drill (click salesperson):** lists **Sales Invoices** via `frappe.desk.reportview.get` / `frappe.client.get_list` with **`Sales Team.sales_person`** (child table). Resolves BA labels to Sales Person names with fuzzy match (e.g. Mohammed ≈ Mohammmed). Does **not** query parent `sales_person` (417) or list the Sales Team child doctype directly (often 403).

**Line items (invoice tap):** OAuth mobile roles on live often **cannot** `frappe.client.get` Sales Invoice or list `Sales Invoice Item` (**403**). Mobile then shows “line items aren’t available”. **Required for items to work — pick one:**

1. **Permissions (ERPNext):** grant the mobile / OAuth role **read** on `Sales Invoice` (and typically `Sales Invoice Item`), **or**
2. **BA API (preferred):** extend `get_salesperson_performance` (or add `get_salesperson_invoice_detail`) so a request with `salesperson` + `invoice` returns `items[]` server-side (method runs with backend privileges). Example item row: `{ item_code, item_name, qty, amount|sales, gp?, gp_pct? }`.

Preferred long-term: BA returns nested `invoices[]` → `items[]` on drill so mobile need not use Desk form APIs.

Optional BA nested shape (if implemented later): `customers[]` → `invoices[]` → `items[]` on the ranking payload.

**Salesperson row fields (no target):** `name` (or `salesperson`), `sales` (or `total_sales`), `sales_ly`, `growth_pct`, `gp`, `gp_pct`, `collection` (amount paid/collected in period), `outstanding`, `overdue`, `invoice_count`, optional `customers[]`.

**Current live payload (incomplete — only ranking sales):** each row is currently  
`{ salesperson, total_sales, invoice_count, rank }`  
Mobile shows sales + invoice count only until the fields below are added.

**Important — all periods must return the same row shape.**  
MTD currently returns full KPIs (`gp`, `collection`, `outstanding`, …) but **YTD / QTD often return only** `salesperson`, `total_sales`, `invoice_count`, `rank`. That is a backend bug: use `from_date`/`to_date` for filtering and always compute the same KPI columns regardless of `period`.

**Required row shape for full cards:**

```json
{
  "salesperson": "Joseph Axly",
  "total_sales": 95487,
  "invoice_count": 12,
  "rank": 1,
  "gp": 28000,
  "gp_pct": 29.3,
  "collection": 70000,
  "outstanding": 40000,
  "overdue": 12000,
  "sales_ly": 80000,
  "growth_pct": 19.4
}
```

| Field | Meaning |
| ----- | ------- |
| `gp` | **Gross profit** = period sales − **COGS** (stock valuation / buying amount from SLE or item valuation rate × qty). Must **not** equal `total_sales` when items have cost. Do **not** use net total, grand total, or “sales − tax” as GP. |
| `gp_pct` | `gp ÷ total_sales × 100` (same sales base as `total_sales`). Prefer returning both `gp` and optional `cogs`; mobile recomputes %. If valuation is missing (GP ≈ sales / % ≥ ~95), fix COGS on the server — mobile will hide those chips rather than show ~100% margins. |
| `cogs` | Optional. Sum of cost of goods for the same invoices/period. If sent, mobile can derive `gp = sales − cogs`. |
| `collection` | Amount **paid/collected in the same `from_date`–`to_date` window as `total_sales`**. Must be period-scoped Payment Entries (Receive) for that salesperson’s customers. **Do not** return lifetime / all-time collections — that makes Collected >> Sales on MTD (e.g. sales 540 vs collection 33K). Period collections *can* exceed period sales when customers pay older invoices, but should still be date-filtered. |
| `outstanding` | Open AR **as of to_date** for that salesperson’s customers (point-in-time; OK if > period sales) |
| `overdue` | Overdue portion of outstanding as of to_date (point-in-time) |
| `sales_ly` | Same-period sales last year. Use `null` / omit when none — **do not send 0** (UI would show fake “vs LY SAR 0”) |
| `growth_pct` | Optional; mobile can derive from sales / sales_ly. Omit when `sales_ly` is missing |

Mobile also accepts aliases: `gross_profit`→`gp`, `collected`/`total_paid`→`collection`, `total_outstanding`→`outstanding`, `previous_year_sales`→`sales_ly`. Nested `metrics` / `kpis` bags are flattened.

If secondary KPIs are omitted, the app shows **—** for those chips (layout stays the same; values are not invented).

**Product row fields:** `name` (or `label` / `key` / level key), `sales` (or `total_sales`), `qty` (or `sold_qty`), `gp`, `gp_pct`, `sales_ly`, `growth_pct`, `invoice_count`, `customer_count`, `asp`.

**Current live payload (incomplete):**  
`{ key, label, total_sales, sold_qty, invoice_count, rank }`  
Mobile shows name, sales, qty, invoices, and **derives ASP** (= sales ÷ sold_qty). GP / GP% / customers / vs LY stay **—** until BA adds those columns (same rule for all `level` values).

Modules: `salesperson`, `product_performance` (default true). Routes: `/salesperson-performance`, `/product-performance`.

### Phase 3C — Customer 360

| Method | Purpose |
| ------ | ------- |
| `erp_analysis.customer.search_customers` | Typeahead / list (`q` or `search`, `company?`, `limit?`) |
| `erp_analysis.customer.get_customer_360` | Full profile + sales / AR / orders / activity / charts |

**Params (`get_customer_360`):** `customer` (required — Customer `name` / id), `company?`, `from_date?`, `to_date?`.

**Whitelisted company:** always use full ERPNext Company name from access scope (e.g. `Printechs Advanced Printing Trading Co.`), never a login stub like `Printechs`.

#### `search_customers` response

Return a list (any of `customers` / `results` / `rows`):

```json
{
  "customers": [
    {
      "id": "Expertise jubail",
      "name": "Expertise jubail",
      "customer_name": "Expertise jubail",
      "customer_group": "Commercial",
      "territory": "Dammam",
      "salesperson": "Ahmed Al-Rashid"
    }
  ]
}
```

- `id` (or `name` / `customer`) = ERPNext Customer link value (what mobile passes back to `get_customer_360`).
- Prefer **`customer_name`** for display. Do **not** put the doctype label `"Customer"` in `name` / `description`.

#### `get_customer_360` response (mobile contract)

Return under Frappe `message` (object, not string). **`customer` must be an object**, not a bare string id.

```json
{
  "meta": {
    "currency": "SAR",
    "company": "Printechs Advanced Printing Trading Co.",
    "from_date": "2026-01-01",
    "to_date": "2026-08-06"
  },
  "customer": {
    "id": "Expertise jubail",
    "name": "Expertise jubail",
    "customer_name": "Expertise jubail",
    "customer_group": "Commercial",
    "territory": "Dammam",
    "salesperson": "…",
    "mobile": "+9665…",
    "email": "…"
  },
  "sales": {
    "today": 0,
    "mtd": 0,
    "ytd": 0,
    "ytd_ly": null,
    "growth_pct": null,
    "gp": null,
    "gp_pct": null,
    "avg_invoice": null,
    "last_invoice_date": "2026-07-15"
  },
  "receivables": {
    "outstanding": 22667.8,
    "overdue": 22667.8,
    "current": 0,
    "avg_monthly_sales": 18500,
    "avg_monthly_paid": 16200,
    "oldest_invoice": "2025-11-18"
  },
  "orders": {
    "open_so_count": 0,
    "open_so_value": 0,
    "pending_delivery": 0,
    "pending_billing": 0,
    "backorder": 0
  },
  "activity": {
    "last_quotation": null,
    "last_sales_order": null,
    "last_delivery": null,
    "last_invoice": "2026-07-15",
    "last_payment": null
  },
  "charts": {
    "months": ["Mar", "Apr", "May", "Jun", "Jul", "Aug"],
    "sales": [12000, 15000, 18000, 16000, 21000, 14000],
    "collection": [10000, 14000, 17000, 15000, 20000, 12000],
    "receivables": [28000, 26000, 25000, 24000, 23000, 22668]
  }
}
```

#### Receivables field definitions (required for mobile UI)

| Field | Definition | Notes |
| ----- | ---------- | ----- |
| `outstanding` | Sum of unpaid Sales Invoice outstanding for this customer (company-scoped) | Total AR balance |
| `overdue` | Portion of outstanding where `due_date` &lt; today | **Not** an aging bucket — any days past due |
| `current` | `outstanding - overdue` (not yet due) | Can be `0` |
| `avg_monthly_sales` | Average monthly invoiced sales for the customer | Prefer: `sum(grand_total of SI in last N months) / N` with N=6 or 12; or YTD ÷ months elapsed |
| `avg_monthly_paid` | Average monthly **amount paid** by the customer (collections) | Prefer: `sum(Payment Entry Receive for party) YTD / months elapsed`. Also accept `monthly_collection` / `monthly_paid` |
| `oldest_invoice` | Oldest open invoice posting/due date (`YYYY-MM-DD`) | Optional |
| `aging_buckets` | Optional map/list of aging amounts | e.g. `{ "Current": 0, "1-30": 0, "31-60": 0, "61-90": 0, "over_90": 0 }` |

**Do not confuse** `avg_monthly_paid` with outstanding AR. It is cash/collection received, not receivables balance.

**Do not send (mobile no longer shows):** `dso`, `credit_limit`, `credit_used`, `available_credit` on this screen. Credit limit is out of scope for this client.

**Optional later (not on UI yet):** aging buckets if useful for a future drill-down:

```json
"aging": {
  "current": 0,
  "1_30": 5000,
  "31_60": 8000,
  "61_90": 2000,
  "over_90": 7667.8
}
```

#### Common bugs to avoid

1. **`customer` as a string** (`"customer": "Expertise jubail"`) — mobile used to show the title **"Customer"**. Always return an **object** with `id` + `customer_name` (or `name`).  
   If you keep `customer` as a string id, you **must** also send a **`profile`** object with `customer_name`, `customer_group`, `territory`, `mobile_no`, `email_id` (mobile maps this).
2. Returning only `overdue` and omitting `outstanding` / `current` — mobile then shows partial dashes.
3. Putting doctype label `"Customer"` in `name` / search `description`.
4. Inventing demo numbers — return `null` / omit when unknown; mobile shows **—**.

#### Live payload shape mobile also accepts

Current production responses often look like:

```json
{
  "customer": "Expertise jubail",
  "company": "Printechs Advanced Printing Trading Co.",
  "profile": { "customer_name": "…", "customer_group": "…", "territory": "…", "mobile_no": "…", "email_id": "…" },
  "receivables": { "outstanding": 0, "overdue": 0, "current": 0, "avg_monthly_sales": 0, "avg_monthly_paid": 0 },
  "recent_invoices": [],
  "open_sales_orders": [],
  "statement": { "total_outstanding": 0, "total_invoiced": 0 }
}
```

Mobile maps `profile` → identity, `open_sales_orders` → orders, `recent_invoices` → activity, `statement` → AR/sales fallbacks. Prefer the contract shape above for new work; both are supported.

#### Related APIs mobile already uses

- `erp_analysis.receivables.get_customer_statement` — statement PDF / email + fallback AR enrich (`total_outstanding`, `total_invoiced`, `items[]` with `due_date`, `outstanding`).
- Module flag: `modules.customer_360` (default `true`). Route: `/customer-360`.

### Phase 3D — Collection Performance + Attention

| Method | Purpose |
| ------ | ------- |
| `erp_analysis.collection.get_collection_dashboard` | KPIs + breakdown by territory / salesperson / customer + optional charts |
| `erp_analysis.collection.get_collection_attention` | Accounts needing follow-up (overdue / priority) |

**Params (common):** `company?`, `from_date?`, `to_date?`, `period?`, `territory?`, `salesperson?`, `customer?`, `limit?` (attention).

**KPIs (actuals only — no target/achievement):** `today`, `mtd`, `ytd`, `ytd_ly?`, `growth_pct?`, `payment_count?`, `avg_payment?`.

**Breakdown row:** `id`, `name`, `collected` (or `collection`), `growth_pct?`, `outstanding?`, `overdue?`, `payment_count?`.

**Attention item:** `customer` / `customer_id`, `outstanding`, `overdue?`, `days_overdue?`, `priority` (`high`|`medium`|`low`), `reason?`, `salesperson?`, `territory?`, `mobile?`, `email?`, `last_payment?`.

Module: `collection` (default true). Route: `/collection-dashboard`. **Do not** send or display collection target %.

### Phase 3E — Sales Order / Order Book

| Method | Purpose |
| ------ | ------- |
| `erp_analysis.sales_orders.get_sales_order_dashboard` | KPIs + open SO list + breakdown + aging/charts |

**Params:** `company?`, `from_date?`, `to_date?`, `period?`, `territory?`, `salesperson?`, `customer?`, `status?`, `limit?`.

**KPIs:** `open_so_value`, `open_so_count`, `pending_delivery`, `pending_billing`, `backorder`, `booked_today` / `booked_mtd` / `booked_ytd`, `avg_order_value`.

**Optional sections:** `orders[]` (open SO lines), `by_customer` / `by_salesperson` / `by_territory`, `aging[]` (`label`, `value`, `count?`), `charts` (`months`, `booked`, `delivered`).

Module: `sales_orders` (default true). Route: `/sales-order-dashboard`.

### Phase 3F — Payables + Payment Planning

| Method | Purpose |
| ------ | ------- |
| `erp_analysis.payables.get_payables_dashboard` | KPIs, aging, suppliers, open invoices, charts |
| `erp_analysis.payables.get_payment_planning` | Due-this-week / month summary + suggested payment list |

**Params (common):** `company?`, `from_date?`, `to_date?`, `period?`, `supplier?`, `limit?`.

**KPIs:** `total`, `overdue`, `overdue_pct`, `current`, `dpo`, `invoice_count`, `paid_mtd`, `paid_ytd`.

**Planning summary:** `due_this_week`, `due_next_week`, `due_this_month`, `overdue_to_pay`. Plan item: `supplier`, `amount`, `due_date`, `priority`, `invoice?`.

Module: `payables` (default true). Route: `/payables-dashboard`.

### Phase 3G — Purchase Performance

| Method | Purpose |
| ------ | ------- |
| `erp_analysis.purchase.get_purchase_dashboard` | KPIs, open PO book, supplier/category breakdown, status, charts |

**Params:** `company?`, `from_date?`, `to_date?`, `period?`, `supplier?`, `category?`, `status?`, `limit?`.

**KPIs:** `today` / `mtd` / `ytd`, `open_po_value` / `open_po_count`, `pending_receipt`, `pending_billing`, `supplier_count`, `avg_order_value`, `avg_lead_time`.

**Optional sections:** `by_supplier`, `by_category`, `by_status`, `orders[]`, `charts` (`months`, `purchased`, `received`).

Module: `purchase` (default true). Route: `/purchase-performance-dashboard`.

### Phase 3H — Inventory Health / Stock Cover / Dead Stock

| Method | Purpose |
| ------ | ------- |
| `erp_analysis.inventory.get_inventory_health` | KPIs + low/overstock lists + warehouse/category |
| `erp_analysis.inventory.get_stock_cover` | Days of cover by item |
| `erp_analysis.inventory.get_dead_stock` | Non-moving / idle stock (`old_days?`) |

**Params (common):** `company?`, `warehouse?`, `category?`, `brand?`, `limit?`. Dead stock also: `old_days?` (default 90).

**Health KPIs:** `total_value`, `low_stock_count` / `value`, `overstock_*`, `non_moving_*`, `turnover`, `days_of_cover`, `sku_count`.

Module: `inventory_health` (default true). Route: `/inventory-health` (classic inventory dashboard remains `/inventory-dashboard`).

### Phase 3I — Profitability (Gross Profit)

| Method | Purpose |
| ------ | ------- |
| `erp_analysis.profitability.get_profitability_dashboard` | Sales / COGS / GP KPIs + breakdowns + monthly charts |

**Params:** `company?`, `from_date?`, `to_date?`, `period?`, dimension filters (`territory`, `salesperson`, `customer`, `brand`, `division`).

**KPIs:** `sales`, `cogs`, `gp`, `gp_pct`, LY compares, `invoice_count`.  
Accept MetricPoint shape (`{ "value": number }`) or plain numbers. Flat root fields (`total_sales`, `gross_profit`, …) are also mapped. Mobile falls back to live `sales_kpis` / dashboard sales when BA returns empty KPIs.

**Breakdowns:** `by_customer`, `by_product`, `by_salesperson`, `by_territory`, `by_brand` — row fields `sales`, `cogs`, `gp`, `gp_pct`, `growth_pct?`.

Module: `profitability` (default true). Route: `/profitability-dashboard`.

### Phase 3J — Management Exceptions

| Method | Purpose |
| ------ | ------- |
| `erp_analysis.exceptions.get_management_exceptions` | Alert list + severity summary (no target-miss until targets return) |

**Params:** `company?`, `from_date?`, `to_date?`, `period?`, `category?`, `severity?`, `limit?`.

**Item fields:** `title`, `category`, `severity` (`critical`|`high`|`medium`|`low`), `message?`, `metric_value?`, `party?`, `reference?`, `route?`.

Module: `exceptions` (default true). Route: `/exceptions-dashboard`.

### Phase 3K — Approval Analytics

| Method | Purpose |
| ------ | ------- |
| `erp_analysis.approvals.get_approval_analytics` | Pending/approved/rejected KPIs, cycle time, by doctype/approver |

**Params:** `company?`, `from_date?`, `to_date?`, `period?`, `doctype?`, `user?`.

**KPIs:** `pending_count`, `approved_count`, `rejected_count`, `avg_cycle_hours`, `median_cycle_hours`, `overdue_pending`, `sla_breach_pct`.

Module: `approval_analytics` (default true). Route: `/approval-analytics`.

### Auth (mobile)

```http
POST /api/method/frappe.integrations.oauth2.get_token
Content-Type: application/x-www-form-urlencoded

grant_type=password&username=...&password=...&client_id=...
```

Refresh:

```http
grant_type=refresh_token&refresh_token=...&client_id=...
```

### v1 BA methods

All must be `@frappe.whitelist()` (guest only where noted).

#### Dashboard / sales

- `erp_analysis.dashboard.get_complete_dashboard_data`
- `erp_analysis.sales_kpis.get_dashboard_kpis`
- `erp_analysis.sales_kpis.get_sales_dashboard`

#### Receivables

- `erp_analysis.receivables.get_receivables_snapshot`
- `erp_analysis.receivables.get_receivables_performance`
- `erp_analysis.receivables.get_receivables_trends`
- `erp_analysis.receivables.get_receivables_dashboard`
- `erp_analysis.receivables.get_territory_receivables`
- `erp_analysis.receivables.get_customer_statement`

#### Customer 360

- `erp_analysis.customer.search_customers`
- `erp_analysis.customer.get_customer_360`

#### Collection

- `erp_analysis.collection.get_collection_dashboard`
- `erp_analysis.collection.get_collection_attention`

#### Sales Orders

- `erp_analysis.sales_orders.get_sales_order_dashboard`

#### Payables

- `erp_analysis.payables.get_payables_dashboard`
- `erp_analysis.payables.get_payment_planning`

#### Purchase

- `erp_analysis.purchase.get_purchase_dashboard`

#### Inventory Health (Phase 3H)

- `erp_analysis.inventory.get_inventory_health`
- `erp_analysis.inventory.get_stock_cover`
- `erp_analysis.inventory.get_dead_stock`

#### Profitability

- `erp_analysis.profitability.get_profitability_dashboard`

#### Exceptions

- `erp_analysis.exceptions.get_management_exceptions`

#### Approval Analytics

- `erp_analysis.approvals.get_approval_analytics`

#### Inventory

- `erp_analysis.inventory.get_inventory_snapshot`
- `erp_analysis.inventory.get_inventory_performance`
- `erp_analysis.inventory.get_inventory_trends`
- `erp_analysis.inventory.get_inventory_risk`
- `erp_analysis.inventory.get_inventory_hierarchy`
  - **Category path (unchanged):** `level=category|brand|item_group|item|warehouse|territory` with Category parents; bare array response.
  - **Territory path (new):** `level=territory|warehouse|brand|item_group|item` with `territory` (+ `warehouse`/`brand`/`item_group`); envelope `{ level, rows, meta }`.
  - WH→territory mapping: warehouse **name/parent contains** territory name (no Warehouse.territory field on site); unmapped omitted.
  - Valuation: Bin `qty × valuation_rate` (same as snapshot). Stock scope: `allow_view_all_stock` / `view_territories`.
  - Aliases: `erp_analysis.stock.get_inventory_hierarchy`, `printechs_utility.inventory.get_inventory_hierarchy` (forward `territory`, `territories`, `limit`).

#### Approvals

- `erp_analysis.approvals.get_all_approvals`
- `erp_analysis.approvals.approve_document`
- `erp_analysis.approvals.reject_document`

#### Access

- `erp_analysis.api.get_my_access`
- `erp_analysis.api.clear_my_access_cache`

#### Employee / profile

- `erp_analysis.employee.get_complete_employees_data`
- `erp_analysis.employee.get_employee_profile`
- `erp_analysis.employee.get_employees`

### Phase 2 (optional)

- `erp_analysis.catalogue.*`
- `erp_analysis.api.store_push_token`
- `erp_analysis.customer_notifications.send_statement_pdf`

---

## Expected package layout

```text
apps/erp_analysis/
  erp_analysis/
    __init__.py          # __version__ = "1.0.0"
    hooks.py
    modules.txt
    patches.txt
    api.py               # health, get_mobile_config, get_my_access, clear_my_access_cache
    config.py            # get_client_id
    oauth_setup.py       # ensure_oauth_client
    dashboard.py
    sales_kpis.py
    receivables.py
    inventory.py
    approvals.py
    employee.py
  pyproject.toml / setup.py
```

Frappe resolves `erp_analysis.api.health` → `erp_analysis/api.py` → `health()`.

---

## Post-install checklist

- [ ] `curl .../api/method/erp_analysis.api.health` returns `ok: true`
- [ ] OAuth Client exists with **Password** grant; client_id known
- [ ] Mobile: save `https://site1.local` (no trailing slash issues)
- [ ] Mobile: login with a real User password
- [ ] Dashboard / receivables / inventory / approvals load (or stubs until logic ported)
- [ ] `bench --site $SITE list-apps` shows `erp_analysis`

---

## Troubleshooting

| Symptom | Likely cause |
| -------- | ------------ |
| Mobile health: “not installed” / 417 | App not installed, or method not whitelisted; run migrate + restart |
| Login: invalid client | Wrong `client_id` or Password grant not enabled on OAuth Client |
| Login: invalid credentials | User/password wrong; user disabled; or not allowed API access |
| 403 on BA methods | User roles / permissions; or method requires login and token missing |
| Timeouts on inventory | Server query too heavy — add caching / indexes in `erp_analysis` |
| **`unexpected keyword argument 'cmd'`** | Wrapper forwarded Frappe’s `cmd` into `printechs_utility`. Run **`docs/erp_analysis/fix_cmd_kwargs.sh`** on the server, then restart. |
| **`unexpected keyword argument 'from_date'`** (inventory trends) | Mobile was sending date range; server method takes `months`. App fixed to send `months`. Re-run **`fix_cmd_kwargs.sh`** for signature-aware filtering. |

### Fix `cmd` kwargs error (run on server now)

```bash
# Copy docs/erp_analysis/fix_cmd_kwargs.sh to the server, then:
chmod +x ~/fix_cmd_kwargs.sh
export BENCH_PATH="$HOME/frappe-bench"
export MIGRATE_FROM_PRINTECHS=1
~/fix_cmd_kwargs.sh
```

This rewrites the proxy modules so they strip `cmd` (and related keys) before calling `printechs_utility`.

---

## Related mobile files

- `src/api/endpoints.ts` — path constants
- `src/api/mobileConfig.ts` — health + `get_mobile_config` client
- `src/api/oauth.ts` — password grant login
- `src/api/demoMode.ts` — empty URL = demo
