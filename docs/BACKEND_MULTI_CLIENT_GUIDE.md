# Backend guide — multi-client mobile config (`erp_analysis`)

Use this on **every ERPNext site** that runs the Printechs mobile app.
The mobile app reads **one config API** after login and adapts UI + request params from it.

All BA logic lives in **`erp_analysis`** (no `printechs_utility` proxies).

---

## 1. What you control

**Preferred:** Desk → **Mobile App Settings** (Single DocType, per site).

**Fallback:** code defaults in `erp_analysis/mobile_config.py` (used when settings are unset).

| Key | Effect on mobile |
| --- | ---------------- |
| `modules.<name>: false` | Hides that area (tabs / dashboard cards) |
| `dimensions.<name>: false` | Does **not** send that filter; hides related charts/labels |
| `apis.<method>: false` | Skips that API call; shows empty section (no crash) |
| Empty / missing arrays in BA responses | Always OK — app soft-parses and hides empty charts |

**Precedence:** Mobile App Settings (Desk) → code defaults. `get_my_access` still applies for permissions.

---

## 2. Edit config on a site (Desk)

1. Desk → **Mobile App Settings**
2. Toggle Modules / Dimensions
3. **Disabled API Methods** — comma-separated method names
4. Optional **Dashboards JSON** override
5. Save → `bench --site SITE clear-cache && bench restart`

Verify:

```bash
curl -s "https://YOUR_SITE/api/method/erp_analysis.api.get_mobile_config" \
  -H "Authorization: Bearer ACCESS_TOKEN"
```

Code defaults: edit `erp_analysis/mobile_config.py` only for shipped global defaults.

---

## 3. Response shape

Includes `modules`, `dimensions`, `apis`, and `dashboards`. See `ERP_ANALYSIS_API_CONTRACT.md` for the full JSON example.

---

## 4. Client recipes

| Recipe | Desk action |
|--------|-------------|
| Full (Printechs) | Leave defaults |
| No Division/Department | Uncheck dimension Division, Department |
| No Territory | Uncheck Territory; disable `get_territory_receivables` |
| No Inventory | Uncheck module Inventory |
| APIs not ready | Add methods to Disabled API Methods |

Known method names: see `mobile_config.KNOWN_API_METHODS` in code.

---

## 5. Checklist per site

- [ ] `install_erp_analysis.sh` + `bench migrate`
- [ ] OAuth Password grant + `client_id`
- [ ] Mobile App Settings configured
- [ ] Health + config curl tests
- [ ] Mobile login smoke test

---

## 6. Related files

- `erp_analysis/mobile_config.py` — defaults + merge
- `erp_analysis/api.py` — whitelist entry
- `erp_analysis/erp_analysis/doctype/mobile_app_settings/` — Desk UI

Legacy `fix_cmd_kwargs.sh` is **not** needed on new installs.
