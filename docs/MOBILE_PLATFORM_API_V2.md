# Mobile Platform API v2

Contract for authenticated mobile clients using `erp_analysis` bootstrap, access guards, and generic analytics.

**Legacy clients** must continue using `erp_analysis.api.get_mobile_config` until migrated. All v2 endpoints are additive; existing method paths and response shapes are unchanged unless noted.

---

## Versioning

| Field | Location | Meaning |
|-------|----------|---------|
| `schema_version` | Bootstrap + new analytics APIs | Contract shape version (currently `1`) |
| `api_version` | Bootstrap `meta` | App package version from `erp_analysis.__version__` |

Bump `schema_version` only when breaking the documented JSON shape of v2 endpoints.

---

## Authentication

### Required (v2 analytics, bootstrap, Phase 3 dashboards)

Send a valid Frappe session cookie or OAuth Bearer token (same as existing mobile app).

| Endpoint family | Guest allowed |
|-----------------|---------------|
| `erp_analysis.api.health` | Yes |
| `erp_analysis.config.get_client_id` | Yes |
| Public catalogue listing (if configured) | Per endpoint |
| Bootstrap, analytics, KPIs, receivables, etc. | **No** |

Guest calls to protected methods return `AuthenticationError`.

### OAuth discovery

```
GET /api/method/erp_analysis.config.get_client_id
```

Returns `{ "client_id": "..." }` for the Printechs Mobile OAuth client.

---

## Standard response shape (new APIs)

Legacy endpoints keep their existing shapes. **New** generic APIs use:

```json
{
  "data": {},
  "meta": {
    "schema_version": 1
  }
}
```

Bootstrap is a top-level object (not wrapped in `data`) for clarity; it includes `schema_version` at the root and in `meta`.

---

## Bootstrap

**Endpoint:** `GET/POST /api/method/erp_analysis.api.get_mobile_bootstrap`  
**Auth:** Required

Legacy alternative: `erp_analysis.api.get_mobile_config` (unchanged).

### Request

The server resolves everything from the logged-in user. **Do not send** profile ID, customer ID, or physical field names.

| Parameter | Description |
|-----------|-------------|
| `company` | Optional. Honored only when it matches the user's Access Profile company |

### Response (`schema_version: 1`)

```json
{
  "schema_version": 1,
  "api_version": "1.0.0",
  "user": {
    "email": "user@example.com",
    "full_name": "User Name",
    "image_url": null
  },
  "context": {
    "company": "Example Company",
    "profile": "PRINTECHS-B2B",
    "business_type": "B2B",
    "branch": "Jeddah",
    "territory": "Jeddah",
    "view_territories": ["Jeddah"],
    "approve_territories": ["Jeddah"]
  },
  "branding": {
    "app_title": "Business Insight",
    "app_subtitle": "",
    "primary_locale": "en",
    "currency_source": "Company Default"
  },
  "modules": [
    {
      "key": "sales",
      "label": "Sales",
      "enabled": true,
      "route_key": "sales",
      "icon_key": null,
      "feature_key": null
    }
  ],
  "dimensions": [
    {
      "key": "territory",
      "label": "Territory",
      "data_type": "Link",
      "filterable": true,
      "groupable": true,
      "sortable": false
    }
  ],
  "dashboard": [],
  "permissions": {
    "scope": {},
    "objects": []
  },
  "capabilities": {
    "allow_view_all_sales": false,
    "allow_view_all_stock": false,
    "allow_all_receivable": false
  },
  "meta": {
    "schema_version": 1,
    "api_version": "1.0.0",
    "config_source": "mobile_app_settings"
  }
}
```

### Resolution rules

1. **Mobile App Profile:** Access Profile `mobile_app_profile` link → Mobile App Settings `default_mobile_app_profile` → none (legacy `get_mobile_config` behavior).
2. **Modules:** Profile modules ∩ Mobile App Settings toggles ∩ Access Profile API permissions (when user has Access Profile).
3. **Dimensions:** From Mobile App Profile when linked; otherwise Mobile App Settings / code defaults.
4. **Physical ERPNext field names are never returned** in dimension metadata.

### Modules (logical keys)

Common module keys:

`sales`, `executive`, `collection`, `sales_performance`, `sales_orders`, `receivables`, `inventory`, `payables`, `purchase`, `customer_360`, `profitability`, `exceptions`, `approval_analytics`, `approvals`, `catalogue`, `push`, `settings`

Disabled modules are omitted or returned with `enabled: false` per bootstrap builder rules.

### Dashboard widgets

When a Mobile App Profile is linked, `dashboard` lists widget metadata (`key`, `label`, `widget_type`, `module_key`, …). Legacy sites use widgets from Mobile App Settings `dashboards_json`.

Each profile widget is loaded dynamically via **`get_dashboard_widget_data`** (see below). Legacy v1 home screens ignore `widget_type` and call hard-coded APIs per widget id.

---

## Dashboard widget data (v2 dynamic home)

**Endpoint:** `GET/POST /api/method/erp_analysis.api.get_dashboard_widget_data`  
**Auth:** Required (same as bootstrap)

### Request

| Parameter | Required | Description |
|-----------|----------|-------------|
| `widget_key` | Yes | Bootstrap `dashboard[].key` (e.g. `sales_card`) |
| `company` | No | Honored only when it matches Access Profile company |
| `from_date` | No | ISO date; chart widgets only |
| `to_date` | No | ISO date; chart widgets only |
| `limit` | No | Max rows (default `10`) |
| `dimension` | No | Override group-by logical key (drill-down) |
| `filters` | No | JSON object `{ "brand": ["NIKE"], "territory": ["Jeddah"] }` |
| `drill_depth` | No | Index into widget `config.drill_path` (alternative to `dimension`) |

The server resolves widget metadata from the user's Mobile App Profile (metric, dimension, `widget_type`) merged with code defaults in `WIDGET_DEFAULTS`.

Optional **Config JSON** on the widget row (Desk):

```json
{
  "drill_path": ["brand", "territory", "salesperson"],
  "drill_chart_type": "BAR"
}
```

Bootstrap returns parsed `config` on each `dashboard[]` item. `drill_chart_type` is a mobile hint only (server does not enforce chart type per depth yet).

### Response shapes

**Chart widgets** (`PIE`, `DONUT`, `BAR`, `LINE`, `RANKING`):

```json
{
  "widget_key": "sales_card",
  "widget_type": "PIE",
  "label": "Sales Performance",
  "chart": {
    "series": [
      {"label": "Riyadh", "value": 250000.0, "dimension_value": "Riyadh"},
      {"label": "Jeddah", "value": 125000.5, "dimension_value": "Jeddah"}
    ],
    "metric": "net_sales",
    "dimension": "territory",
    "filters": {"brand": ["NIKE"]}
  },
  "meta": {
    "schema_version": 1,
    "render_hint": "pie",
    "drill_path": ["brand", "territory", "salesperson"],
    "drill_depth": 1,
    "next_dimension": "salesperson",
    "drillable": true
  }
}
```

**Drill-down request** (user tapped brand slice `NIKE`, show territories):

```
GET /api/method/erp_analysis.api.get_dashboard_widget_data
  ?widget_key=sales_by_brand
  &dimension=territory
  &filters={"brand":["NIKE"]}
  &limit=10
```

Or use `drill_depth=1` when `config.drill_path` is set on the widget (same example if path is `["brand","territory",...]`).

Response `meta` fields for drill UX:

| Field | Meaning |
|-------|---------|
| `drill_path` | Ordered dimensions from profile `config_json` |
| `drill_depth` | Current index in `drill_path`, if known |
| `next_dimension` | Suggested group-by for the next tap |
| `drillable` | `true` when another drill level exists |
| `chart.filters` | Filters applied to this query |

**Legacy list/KPI widgets** (`LIST`, `KPI`, `TABLE`):

```json
{
  "widget_key": "receivables_card",
  "widget_type": "LIST",
  "label": "Receivables",
  "data": {},
  "meta": {
    "schema_version": 1,
    "legacy_method": "erp_analysis.receivables.get_receivables_dashboard",
    "render_hint": "list"
  }
}
```

`data` keeps the existing legacy API shape (unchanged).

**MATRIX:** Returns `ValidationError` until secondary-dimension analytics is implemented.

### Mobile home flow (v2)

1. `get_mobile_bootstrap` → read `dashboard[]`
2. For each widget, `GET get_dashboard_widget_data?widget_key=<key>`
3. Render by `widget_type` / `meta.render_hint`:
   - `PIE` / `DONUT` / `BAR` / `LINE` / `RANKING` → `chart.series`
   - `LIST` / `KPI` / `TABLE` → `data` (legacy layout)

Legacy v1 continues to use `get_mobile_config` + per-widget hard-coded APIs until the app migrates.

### Chart drill-down (mobile)

See [§10 Chart drill-down](./MOBILE_PHASE3_INTEGRATION.md#10-chart-drill-down-mobile-v2) in the Phase 3 integration guide for copy-paste mobile service code.

---

## Access guards (Phase G)

Central helpers in `erp_analysis.access_context`:

| Helper | Purpose |
|--------|---------|
| `guard_mobile_api()` | Auth + company + optional module/object + view territory scope |
| `get_effective_company()` | Access Profile company wins; rejects cross-company requests |
| `get_effective_view_territories()` | View territory list for analytics |
| `get_effective_approve_territories()` | Approve territory list for inbox/actions |
| `resolve_view_territory_scope()` | Final SQL filter list (honors overrides + requested territory) |
| `resolve_stock_warehouse_scope()` | Warehouse filter derived from profile territories |
| `require_module_access()` | Mobile App Profile module + Access Profile module gate |
| `require_object_access()` | Access Profile line gate by registry `object_key` |
| `assert_customer_in_view_scope()` | Customer 360 read guard |

### Permission behavior

| User type | Company | Territories | Modules |
|-----------|---------|-------------|---------|
| **No Access Profile** (typical Desk / admin) | Request param or user default | No profile filter unless client requests territory | All settings-enabled modules |
| **Access Profile mobile user** | Fixed to profile company | View / approve lists enforced | Intersection of profile + Access Profile lines |
| **Guest** | — | — | Blocked on protected APIs |

Override flags (Access Profile only):

- `allow_view_all_sales` — view territories ignored for **sales** analytics modules
- `allow_view_all_stock` — territory-based warehouse filter skipped for stock
- `allow_all_receivable` — view territories ignored for **receivables** modules

**Approve territories** are separate from **view territories** and apply to approvals inbox/actions only.

### Territory injection (client filter safety)

Clients may send logical filters such as `territory`, `company`, or `brand`. The server:

1. Accepts only **logical dimension keys** registered for the user/site.
2. Validates territory filter values against `resolve_territory_scope()` — out-of-scope values raise `PermissionError`, not silent widening.
3. Applies profile territory SQL in addition to validated filters (intersection).

Desk users without an Access Profile are **not** territory-scoped by default.

---

## Errors

| Condition | Exception | HTTP |
|-----------|-----------|------|
| Guest / no auth | `AuthenticationError` | 401 |
| Company outside Access Profile | `PermissionError` | 403 |
| Territory outside Access Profile | `PermissionError` | 403 |
| Module / object not permitted | `PermissionError` | 403 |
| Unknown dimension / metric / invalid JSON | `ValidationError` | 417 |
| Mandatory parameter missing | `MandatoryError` / `ValidationError` | 417 |

API responses must not include Python tracebacks, SQL text, or internal paths. Details are logged server-side.

---

## Pagination

Legacy list endpoints use mixed patterns. New/generic APIs:

| Parameter | Default | Max | Notes |
|-----------|---------|-----|-------|
| `limit` | 50 | 200 | Row count |
| `offset` | 0 | — | Where supported (e.g. salesperson invoices) |

Paginated legacy responses may include:

```json
{
  "pagination": { "limit": 50, "offset": 0, "count": 12, "total": 120 }
}
```

---

## Dates

| Context | Format | Example |
|---------|--------|---------|
| Request params `from_date`, `to_date` | ISO date `YYYY-MM-DD` | `2026-08-01` |
| Response period blocks | ISO date strings | `"from_date": "2026-08-01"` |
| Datetime fields | ISO date or site datetime string | As returned by Frappe |

Default periods when dates omitted:

- **MTD** — first day of current month through today (most sales/collection APIs)
- **YTD** — Jan 1 through today (KPI blocks)
- **today** — single day

---

## Currency and numbers

- Amounts in API payloads are **numbers** (float), typically **company base currency** (`base_net_total`, `base_paid_amount`, etc.).
- Rounding: 2 decimal places for currency in most KPI/analytics responses unless noted.
- Percentages: e.g. `gp_pct`, `overdue_pct` as 0–100 float with up to 2 decimals.
- Currency code is **not** repeated on every row; use company default from bootstrap `context.company` or ERPNext Company settings.

---

## Generic analytics (Phase D)

All endpoints require authentication. Logical keys only — never `source_field` or DocType names.

### `erp_analysis.analytics.get_dimensions`

Returns enabled dimensions for the logged-in user.

```json
{
  "data": [
    {
      "key": "territory",
      "label": "Territory",
      "data_type": "Link",
      "filterable": true,
      "groupable": true,
      "sortable": false
    }
  ],
  "meta": { "schema_version": 1, "count": 1 }
}
```

### `erp_analysis.analytics.get_dimension_values`

| Parameter | Required | Description |
|-----------|----------|-------------|
| `dimension` | Yes | Logical key e.g. `territory`, `brand` |
| `search` | No | Optional text filter |
| `limit` | No | Default 50, max 200 |
| `company` | No | Must match Access Profile company |

Territory values are pre-filtered to the user's view scope when applicable.

### `erp_analysis.analytics.get_sales_analysis`

| Parameter | Required | Description |
|-----------|----------|-------------|
| `dimension` | Yes | Group-by logical key |
| `metric` | No | `net_sales` (default), `gross_sales`, `sales_qty`, `transactions`, `average_transaction` |
| `from_date` / `to_date` | No | Default: MTD |
| `filters` | No | JSON object of logical keys → value arrays |
| `limit` | No | Default 50 |
| `order` | No | `desc` (default) or `asc` |
| `company` | No | Scoped to Access Profile when set |

Example filters:

```json
{
  "filters": {
    "brand": ["NIKE", "ADIDAS"],
    "territory": ["Jeddah"]
  }
}
```

Response:

```json
{
  "data": [
    {
      "dimension_value": "Jeddah",
      "label": "Jeddah",
      "metric_value": 125000.5,
      "rank": 1
    }
  ],
  "meta": {
    "schema_version": 1,
    "from_date": "2026-08-01",
    "to_date": "2026-08-13",
    "dimension": "territory",
    "metric": "net_sales",
    "count": 1
  }
}
```

`secondary_dimension` is not supported yet.

---

## Legacy endpoint compatibility

The mobile app continues to call methods registered in `Access Object Registry` and documented in `mobile_config.KNOWN_API_METHODS`. Examples:

| Area | Legacy entry points (unchanged) |
|------|----------------------------------|
| Sales KPIs | `erp_analysis.sales_kpis.get_dashboard_kpis` |
| Receivables | `erp_analysis.receivables.*` |
| Inventory | `erp_analysis.inventory.*`, `erp_analysis.stock.*` |
| Approvals | `erp_analysis.approvals.*` |
| Config | `erp_analysis.api.get_mobile_config`, `get_my_access` |

Do not remove or rename legacy whitelisted methods without a mobile app release.

---

## Mobile App Profile setup (opt-in)

Sample profile **`PRINTECHS-B2B`** can be loaded via:

```bash
bench --site <site> execute erp_analysis.scripts.load_printechs_b2b_profile.ensure_profile
```

This creates the profile document only. It does **not**:

- Link Access Profiles
- Set Mobile App Settings default
- Change Desk users or permissions

Link manually in Desk when ready: Access Profile → Mobile App Profile, or Mobile App Settings → Default Mobile App Profile.

---

## Changelog

| Phase | Added |
|-------|--------|
| A | Auth on sensitive APIs |
| B | Mobile App Profile DocTypes |
| C | `get_mobile_bootstrap` |
| D | Generic analytics APIs |
| G | Central access guards |
| H | This contract document |
| J | Optional `PRINTECHS-B2B` profile fixture |
