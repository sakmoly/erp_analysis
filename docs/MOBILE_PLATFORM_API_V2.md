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
