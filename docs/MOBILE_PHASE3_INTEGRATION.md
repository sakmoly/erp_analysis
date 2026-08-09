# Mobile Phase 3 integration guide

**Audience:** Mobile app developers  
**Backend:** `erp_analysis` (all APIs live after Waves 0–6)  
**Config API:** `erp_analysis.api.get_mobile_config`

The BA mobile app repo is **not** in this bench workspace. Use this doc when wiring screens in your mobile project.

---

## 1. How the app should boot

After OAuth login:

1. `GET /api/method/erp_analysis.api.get_mobile_config`
2. `GET /api/method/erp_analysis.api.get_my_access?company=...`
3. Show tabs/cards only where `modules.<key> === true`
4. Before each API call, skip if `apis.<method> === false`
5. Gate Phase 3 screens on **both** module flag **and** Access Object Registry permission

---

## 2. Phase 3 module flags (`get_mobile_config.modules`)

| Module key | Default | Screen / area |
|------------|---------|---------------|
| `executive` | `true` | Executive dashboard 2.0 |
| `collection` | `false` | Collection performance + attention |
| `sales_performance` | `false` | Salesperson & product ranking |
| `sales_orders` | `false` | Order book + open SO list |
| `payables` | `false` | AP dashboard + payment planning |
| `purchase` | `false` | Open PO dashboard + list |
| `customer_360` | `false` | Customer detail (or receivables drill-down) |
| `profitability` | `false` | Gross profit dashboard |
| `exceptions` | `false` | Management exceptions |
| `approval_analytics` | `false` | Approval summary (inbox stays `approvals`) |

**Not in scope (do not add):** `sales_target`, `cash_flow`

Enable per site: Desk → **Mobile App Settings** → Phase 3 Modules.

---

## 3. Phase 3 API endpoints

Base URL: `/api/method/erp_analysis.<module>.<method>`

| Method short name | Full path | Params (common) |
|-------------------|-----------|-----------------|
| `get_executive_dashboard` | `executive.get_executive_dashboard` **or** `dashboard.get_executive_dashboard` | `company`, `from_date`, `to_date`, `territory` |
| `get_collection_dashboard` | `collection.get_collection_dashboard` | `company`, `from_date`, `to_date`, `territory`, `limit` |
| `get_collection_attention` | `collection.get_collection_attention` | `company`, `min_unallocated`, `limit` |
| `get_salesperson_performance` | `sales.get_salesperson_performance` (mobile) · also `sales_performance.*`, `sales_kpis.*` | `company`, `period` (`mtd`/`ytd`/`today`/`yesterday`/`prev_month`), `limit` |
| `get_product_performance` | `sales.get_product_performance` (mobile) · also `sales_performance.*`, `sales_kpis.*` | `company`, `group_by`, `period`, `limit` |
| `get_salesperson_ranking` | `sales_performance.get_salesperson_ranking` | same as above |
| `get_product_ranking` | `sales_performance.get_product_ranking` | `company`, `group_by` (`brand`/`item`/`item_group`), `period`, `limit` |
| `get_order_book_dashboard` | `sales_orders.get_order_book_dashboard` | `company`, `territory`, `limit` |
| `get_open_sales_orders` | `sales_orders.get_open_sales_orders` | `company`, `status`, `pending_delivery_only`, `limit`, `offset` |
| `get_payables_dashboard` | `payables.get_payables_dashboard` | `company`, `limit` |
| `get_payment_planning` | `payables.get_payment_planning` | `company`, `days_ahead`, `limit` |
| `get_purchase_dashboard` | `purchase.get_purchase_dashboard` | `company`, `limit` |
| `get_open_purchase_orders` | `purchase.get_open_purchase_orders` | `company`, `status`, `pending_receipt_only`, `limit`, `offset` |
| `get_customer_360` | `customer_360.get_customer_360` | `customer` (required), `company`, `invoice_limit`, `open_so_limit` |
| `get_stock_cover` | `inventory.get_stock_cover` | `company`, `warehouse`, `lookback_days`, `limit` |
| `get_gross_profit_dashboard` | `profitability.get_gross_profit_dashboard` | `company`, `period`, `limit` |
| `get_management_exceptions` | `exceptions.get_management_exceptions` | `company`, `limit`, `stale_days` |
| `get_approval_summary` | `approval_analytics.get_approval_summary` | `company`, `from_date`, `to_date` |

**v1 unchanged:** `dashboard.get_complete_dashboard_data`, `receivables.*`, `inventory.get_inventory_snapshot`, `approvals.get_all_approvals`, etc.

---

## 4. Suggested navigation map

```
Home (dashboards_json widgets)
├── executive_card      → get_executive_dashboard
├── sales_card          → v1 sales / get_dashboard_kpis
├── collection_card     → get_collection_dashboard
├── receivables_card    → v1 receivables
├── orders_card         → get_order_book_dashboard
├── inventory_card      → v1 inventory + optional get_stock_cover
└── exceptions_card     → get_management_exceptions

More / Analytics
├── Sales Performance   → get_salesperson_ranking, get_product_ranking
├── Payables            → get_payables_dashboard, get_payment_planning
├── Purchase            → get_purchase_dashboard, get_open_purchase_orders
├── Profitability       → get_gross_profit_dashboard
└── Approval Analytics  → get_approval_summary (separate from inbox)

Receivables drill-down
└── Customer row tap    → get_customer_360 (if module_customer_360)
                         → get_customer_statement (existing)
```

---

## 5. Example `dashboards_json` (Mobile App Settings)

```json
[
  {
    "id": "home",
    "title": "Dashboard",
    "module": "sales",
    "widgets": [
      {"id": "executive_card", "type": "expandable", "title": "Executive", "module": "executive"},
      {"id": "sales_card", "type": "expandable", "title": "Sales Performance"},
      {"id": "collection_card", "type": "expandable", "title": "Collection", "module": "collection"},
      {"id": "receivables_card", "type": "expandable", "title": "Receivables"},
      {"id": "orders_card", "type": "expandable", "title": "Order Book", "module": "sales_orders"},
      {"id": "inventory_card", "type": "expandable", "title": "Inventory"},
      {"id": "exceptions_card", "type": "expandable", "title": "Exceptions", "module": "exceptions"}
    ]
  }
]
```

Widgets with `"module": "<key>"` should render only when `modules.<key>` is true.

---

## 6. Access Object Registry keys (add to Access Profile Line)

| object_key |
|------------|
| `erp_analysis.executive.get_executive_dashboard` |
| `erp_analysis.dashboard.get_executive_dashboard` (alias) |
| `erp_analysis.collection.get_collection_dashboard` |
| `erp_analysis.collection.get_collection_attention` |
| `erp_analysis.sales_performance.get_salesperson_ranking` |
| `erp_analysis.sales_performance.get_product_ranking` |
| `erp_analysis.sales_orders.get_order_book_dashboard` |
| `erp_analysis.sales_orders.get_open_sales_orders` |
| `erp_analysis.payables.get_payables_dashboard` |
| `erp_analysis.payables.get_payment_planning` |
| `erp_analysis.purchase.get_purchase_dashboard` |
| `erp_analysis.purchase.get_open_purchase_orders` |
| `erp_analysis.customer_360.get_customer_360` |
| `erp_analysis.inventory.get_stock_cover` |
| `erp_analysis.profitability.get_gross_profit_dashboard` |
| `erp_analysis.exceptions.get_management_exceptions` |
| `erp_analysis.approval_analytics.get_approval_summary` |

Patches `register_phase3_wave2_apis` … `wave6_apis` seed these on migrate.

---

## 7. Rollout checklist (per site)

1. `bench migrate` (erp_analysis patches)
2. Desk → Mobile App Settings → enable Phase 3 modules one at a time
3. Access Profile → add API lines for mobile roles
4. `bench --site SITE clear-cache`
5. Verify config:
   ```bash
   bench --site SITE execute erp_analysis.api.get_mobile_config
   ```
6. Mobile smoke test each enabled screen

---

## 8. Mobile repo

The business analytics mobile app was **not found** in this bench (`frappe-bench/apps/`).  
Only `printechs_support/mobile` (support tickets) exists here.

To wire UI screens, open the BA mobile repo in Cursor (or share its path) and reference this guide.

---

## Related

- [BACKEND_MULTI_CLIENT_GUIDE.md](./BACKEND_MULTI_CLIENT_GUIDE.md)
- [PHASE3_IMPLEMENTATION_PLAN.md](./PHASE3_IMPLEMENTATION_PLAN.md)
- `erp_analysis/mobile_config.py` — `KNOWN_API_METHODS`, defaults
