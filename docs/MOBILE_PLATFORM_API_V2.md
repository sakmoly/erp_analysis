# Mobile Platform API v2 — Bootstrap

**Endpoint:** `GET/POST /api/method/erp_analysis.api.get_mobile_bootstrap`  
**Auth:** Required (Bearer token / session). Guest requests are rejected.

Legacy clients should continue using `erp_analysis.api.get_mobile_config`.

---

## Request

No profile ID or customer ID is accepted. Optional:

| Parameter | Description |
|-----------|-------------|
| `company` | Only honored when it matches the user's Access Profile company |

---

## Response (`schema_version: 1`)

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

---

## Resolution rules

1. **Mobile App Profile:** Access Profile link → Mobile App Settings default → none (legacy config).
2. **Modules:** Mobile App Profile modules ∩ Mobile App Settings toggles ∩ Access Profile API permissions.
3. **Dimensions:** From Mobile App Profile when linked; otherwise from Mobile App Settings / code defaults.
4. **Physical ERPNext field names are never returned** in dimension metadata.

---

## Errors

| Condition | Response |
|-----------|----------|
| Guest / no auth | `AuthenticationError` |
| Company outside Access Profile scope | `PermissionError` |

---

# Access guards (Phase G)

Central helpers live in `erp_analysis.access_context`:

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

Phase 3 APIs wired to these guards include: `sales_performance`, `profitability`, `collection`, `customer_360`, and generic `analytics`.

Territory filters cannot be bypassed by passing arbitrary SQL — only logical keys and validated territory names within the user's scope are accepted.

---

# Generic Analytics (Phase D)

All endpoints require authentication. The client sends **logical dimension keys only** — never field names or DocTypes.

## `erp_analysis.analytics.get_dimensions`

Returns enabled dimensions for the logged-in user (Mobile App Profile or legacy Settings fallback).

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

## `erp_analysis.analytics.get_dimension_values`

| Parameter | Required | Description |
|-----------|----------|-------------|
| `dimension` | Yes | Logical key e.g. `territory`, `brand` |
| `search` | No | Optional text filter |
| `limit` | No | Default 50, max 200 |
| `company` | No | Must match Access Profile company |

```json
{
  "data": [{ "value": "Jeddah", "label": "Jeddah" }],
  "meta": { "schema_version": 1, "dimension": "territory", "count": 1 }
}
```

## `erp_analysis.analytics.get_sales_analysis`

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

Unknown dimensions or metrics return validation errors — never silent SQL injection.

