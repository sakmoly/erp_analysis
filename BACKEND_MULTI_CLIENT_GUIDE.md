# Backend guide — multi-client mobile config (`erp_analysis`)

Use this on **every ERPNext site** that runs the Printechs mobile app.
The mobile app reads **one config API** after login and adapts UI + request params from it.

---

## 1. What you control

Edit **`erp_analysis.api.get_mobile_config`** (file: `apps/erp_analysis/erp_analysis/api.py`).

| Key | Effect on mobile |
| --- | ---------------- |
| `modules.<name>: false` | Hides that area (tabs / dashboard cards) |
| `dimensions.<name>: false` | Does **not** send that filter; hides related charts/labels |
| `apis.<method>: false` | Skips that API call; shows empty section (no crash) |
| Empty / missing arrays in BA responses | Always OK — app soft-parses and hides empty charts |

**Rule:** Prefer returning **empty lists / null / 0** for unused fields. Never omit required top-level keys if you can help it. Never throw because Division/Department is missing.

---

## 2. Edit config on a site

```bash
cd ~/frappe-bench   # or your BENCH_PATH
nano apps/erp_analysis/erp_analysis/api.py
# edit get_mobile_config() return dict
bench --site YOUR_SITE clear-cache
bench restart
```

Or re-apply the repo script (rewrites wrappers + `api.py`):

```bash
export BENCH_PATH="$HOME/frappe-bench"
export MIGRATE_FROM_PRINTECHS=1
./fix_cmd_kwargs.sh
# then edit dimensions/apis in api.py for that client
```

Verify:

```bash
curl -s "https://YOUR_SITE/api/method/erp_analysis.api.get_mobile_config" \
  -H "Authorization: Bearer ACCESS_TOKEN"
```

---

## 3. Recommended `get_mobile_config` template

```python
@frappe.whitelist()
def get_mobile_config(**kwargs):
    for _k in ("cmd", "method", "csrf_token", "args", "kwargs"):
        kwargs.pop(_k, None)

    return {
        "app": "erp_analysis",
        "version": "1.0.0",
        "modules": {
            "sales": True,
            "receivables": True,
            "inventory": True,
            "approvals": True,
            "catalogue": False,   # phase 2
            "push": False,        # phase 2
            "settings": True,
        },
        # Turn OFF what this client does not use
        "dimensions": {
            "company": True,
            "territory": True,    # False if no Territory doctype / reports
            "warehouse": True,
            "brand": True,        # False if no Brand
            "division": True,     # False if client has no Division
            "department": True,   # False if HR Department unused
            "cost_center": False,
            "branch": True,
        },
        # Optional: disable specific methods this site has not implemented
        "apis": {
            # "get_inventory_trends": False,
            # "get_inventory_hierarchy": False,
            # "get_territory_receivables": False,
        },
        "dashboards": [
            {
                "id": "home",
                "title": "Dashboard",
                "module": "sales",
                "widgets": [
                    {"id": "sales_card", "type": "expandable", "title": "Sales Performance"},
                    {"id": "receivables_card", "type": "expandable", "title": "Receivables"},
                    {"id": "inventory_card", "type": "expandable", "title": "Inventory"},
                ],
            }
        ],
    }
```

---

## 4. Client recipes

### A) Printechs (full)

Keep defaults — all main modules `true`, Division/Department/Territory `true`.

### B) Client with no Division / Department

```python
"dimensions": {
    "company": True,
    "territory": True,
    "warehouse": True,
    "brand": True,
    "division": False,
    "department": False,
    "cost_center": False,
    "branch": True,
}
```

Mobile will:

- Not show Division charts
- Not show Department on employee list
- Not send `division` / `department` query params

### C) Client with no Territory

```python
"dimensions": {
    ...
    "territory": False,
}
"apis": {
    "get_territory_receivables": False,
}
```

### D) Client without Inventory (or Inventory BA not ready)

```python
"modules": {
    ...
    "inventory": False,
}
```

### E) Method not implemented yet (avoid 417/500 spam)

```python
"apis": {
    "get_inventory_trends": False,
    "get_inventory_hierarchy": False,
    "get_receivables_trends": False,
}
```

Method names = Python function short names, e.g. `get_inventory_snapshot`, `get_all_approvals`.

---

## 5. BA response contract (important)

For **every** BA method the app calls:

1. Keep a **stable JSON shape** (same keys as Printechs / contract).
2. If the client does not use a breakdown, return **`[]`** or **`null`**, not a 500.
3. Numbers that are missing → **`0`**.
4. Profile strings that are missing → **`""`**.

Examples:

```python
# Sales dashboard — no division on this site
"division": []          # or omit; mobile treats as empty
"territory": [...]      # only if dimension.territory is true

# Employee
"department": ""        # fine when dimension.department is false
"departments": []
```

---

## 6. Proxy / kwargs safety (required on all sites)

Frappe always passes `cmd` into whitelisted methods. Wrappers that forward to `printechs_utility` **must**:

1. Strip `cmd`, `method`, `csrf_token`, …
2. Only forward kwargs the target function accepts (`inspect.signature`)

Use repo script:

```bash
export BENCH_PATH="$HOME/frappe-bench"
export MIGRATE_FROM_PRINTECHS=1
./fix_cmd_kwargs.sh
```

Without this, mobile gets: `unexpected keyword argument 'cmd'` / `'from_date'`.

---

## 7. Checklist per new client site

- [ ] Install `erp_analysis` (`install_erp_analysis.sh`)
- [ ] Run `fix_cmd_kwargs.sh` if migrating from `printechs_utility`
- [ ] OAuth Client with **Password** grant; note `client_id`
- [ ] Edit `get_mobile_config` → set `dimensions` / `modules` / `apis` for this client
- [ ] `bench clear-cache && bench restart`
- [ ] Health: `GET /api/method/erp_analysis.api.health`
- [ ] Config: `GET /api/method/erp_analysis.api.get_mobile_config` (with Bearer)
- [ ] Mobile: save site URL → login → confirm hidden sections match config

---

## 8. Reference — dimensions ↔ mobile behaviour

| Dimension | Params stripped when false | UI impact |
| --------- | -------------------------- | --------- |
| `division` | `division` | Sales Division pie / charts |
| `department` | `department` | Employee department line / filters |
| `territory` | `territory`, `territories` | AR by territory, sales territory, approvals territory filter |
| `warehouse` | `warehouse` | Inventory warehouse filters |
| `brand` | `brand` | Brand filters / hierarchy brand level |
| `branch` | `branch` | Branch scope (permissions / profile) |
| `company` | (kept allowed for most calls) | Company scope |
| `cost_center` | `cost_center` | Reserved (default off) |

---

## 9. Related files in mobile repo

- Contract: `docs/ERP_ANALYSIS_API_CONTRACT.md`
- Install: `docs/erp_analysis/install_erp_analysis.sh`
- Kwargs fix + config template: `docs/erp_analysis/fix_cmd_kwargs.sh`
