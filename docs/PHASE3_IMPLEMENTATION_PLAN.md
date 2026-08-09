# Phase 3 — Implementation plan (`erp_analysis`)

**Based on:** [PHASE3_SCOPE.md](../PHASE3_SCOPE.md) (2026-08-05)  
**App:** `erp_analysis` — all new BA logic stays here; **no** `printechs_utility`  
**Mobile contract:** extend v2 additively; **do not break** v1 paths

---

## Principles

| Rule | Detail |
|------|--------|
| **v1 frozen** | Keep `get_complete_dashboard_data`, existing receivables/inventory/approvals paths unchanged until mobile explicitly migrates |
| **Phase 3 = new modules** | New whitelisted methods under `erp_analysis.<module>.*` |
| **Executive 2.0 = new endpoint** | `erp_analysis.executive.get_executive_dashboard` — do not reshape v1 dashboard payload |
| **Deferred = no stubs** | No target/cash-flow keys, DocTypes, or placeholder APIs (per scope doc) |
| **Empty > error** | Optional blocks return `null` or `[]`; never 500 for missing SO/PO/payables until built |
| **Shared KPIs** | One implementation in `services/kpi/`; dashboard/sales/collection/executive call it |
| **Per-site toggles** | New modules added to `mobile_config.py` + **Mobile App Settings** when mobile screens ship |
| **Permissions** | Each new whitelisted method gets an **Access Object Registry** row (`erp_analysis.<module>.<method>`) |

---

## Target package layout (after Phase 3)

```text
erp_analysis/
├── api.py                    # health, get_mobile_config, access, push
├── mobile_config.py          # modules / dimensions / apis defaults
├── executive.py              # 3A — NEW
├── collection.py             # 3D — NEW
├── sales_orders.py           # 3E — NEW
├── payables.py               # 3F — NEW
├── purchase.py               # 3G — NEW
├── customer_360.py           # 3C — NEW
├── profitability.py          # 3I — NEW (or merge into services + thin API)
├── exceptions.py             # 3J — NEW
├── approval_analytics.py     # 3K — NEW
├── sales_performance.py      # 3B′ — NEW
├── dashboard.py              # v1 — keep
├── sales_kpis.py             # v1 — keep; delegate KPIs to services over time
├── receivables.py              # v1 — extend for collection cross-links only
├── inventory.py              # v1 — 3H mostly done
├── approvals.py              # v1 — keep inbox/actions
├── services/
│   ├── kpi/
│   │   ├── sales.py          # today/mtd/ytd + LY compare
│   │   ├── gross_profit.py   # MTD/YTD GP %
│   │   ├── collection.py     # payment actuals (not AR)
│   │   └── receivables.py    # total/overdue/overdue %
│   ├── sales_orders.py       # open SO queries
│   ├── payables.py           # AP totals
│   └── purchase.py           # open PO queries
└── erp_analysis/doctype/
    └── mobile_app_settings/  # per-site module/dimension toggles
```

---

## Build order (recommended)

### Wave 0 — Foundation (do first)

**Goal:** Shared numbers; no new mobile screens required yet.

| Task | Files | Notes |
|------|-------|-------|
| KPI service layer | `services/kpi/sales.py`, `gross_profit.py`, `collection.py`, `receivables_summary.py` | Extract logic from `dashboard.py` / `sales_kpis.py` gradually |
| RPC helpers | `utils/rpc.py` | Already exists — reuse for date/company/territory resolution |
| Tests (bench console) | — | `bench execute erp_analysis.services.kpi.sales.get_sales_mtd` etc. |

**Endpoints (internal only at first):** no new whitelists until Wave 1.

---

### Wave 1 — 3A Executive Dashboard 2.0

| Item | Value |
|------|-------|
| **Endpoint** | `erp_analysis.executive.get_executive_dashboard` |
| **Auth** | Bearer, `allow_guest=False` |
| **Params** | `company`, `from_date`, `to_date`, optional `territory`, `branch` |

**Response shape (stable top-level keys always present):**

```json
{
  "sales": { "today": 0, "mtd": 0, "ytd": 0, "mtd_ly": 0, "ytd_ly": 0, "mtd_change_pct": 0, "ytd_change_pct": 0 },
  "gross_profit": { "mtd": 0, "ytd": 0, "gp_pct_mtd": 0, "gp_pct_ytd": 0 },
  "collection": { "today": 0, "mtd": 0, "ytd": 0 },
  "receivables": { "total": 0, "overdue": 0, "overdue_pct": 0 },
  "inventory": { "value": 0, "low_stock_count": 0, "non_moving_count": 0 },
  "orders": null,
  "purchasing": null,
  "payables": null,
  "approvals": { "pending_count": 0 }
}
```

| Block | Source (Wave 1) | Until ready |
|-------|-----------------|-------------|
| sales | `services/kpi/sales.py` | — |
| gross_profit | `services/kpi/gross_profit.py` | — |
| collection | `services/kpi/collection.py` | Payment Entry / PE references |
| receivables | `services/kpi/receivables_summary.py` | Wrap existing AR logic |
| inventory | `inventory.get_inventory_snapshot` + risk/non-moving counts | — |
| approvals | `approvals.get_all_approvals` count or lightweight SQL | — |
| orders | `null` | Wave 3 (3E) |
| purchasing | `null` | Wave 4 (3G) |
| payables | `null` | Wave 4 (3F) |

**Mobile config:** add when mobile screen ships:

```python
# mobile_config.py — later wave
"executive": True  # new module flag
```

**Access registry:** `erp_analysis.executive.get_executive_dashboard`

**v1 impact:** none (new path only)

---

### Wave 2 — 3D Collection + 3B′ Sales performance

#### 3D Collection Performance

| Endpoint | Purpose |
|----------|---------|
| `erp_analysis.collection.get_collection_dashboard` | Today/MTD/YTD actuals, by territory/customer tables |
| `erp_analysis.collection.get_collection_attention` | Overdue customers, large unallocated, etc. |

**Data source:** `tabPayment Entry` (submitted), allocated amounts — **not** `receivables.get_*` outstanding.

**Exclude:** any `target`, `achievement_pct`, `remaining_target` fields.

#### 3B′ Salesperson & Product performance

| Endpoint | Purpose |
|----------|---------|
| `erp_analysis.sales_performance.get_salesperson_ranking` | Actual sales MTD/YTD by salesperson |
| `erp_analysis.sales_performance.get_product_ranking` | By item / item group / brand |

Reuse `dashboard.get_top_customers` / `get_top_brands` patterns; add salesperson dimension from Sales Invoice `owner` or custom Sales Team field (site-specific — document in Mobile App Settings notes).

**Mobile module flags (when UI ready):** `collection`, `sales_performance`

---

### Wave 3 — 3E Sales Order / Order Book

| Endpoint | Purpose |
|----------|---------|
| `erp_analysis.sales_orders.get_order_book_dashboard` | Open SO value/count, pending delivery |
| `erp_analysis.sales_orders.get_open_sales_orders` | Paginated list |

**Then:** backfill `executive.orders` from `services/sales_orders.py`.

**Mobile module:** `sales_orders`

---

### Wave 4 — 3F Payables + 3G Purchase

| Module | Endpoints |
|--------|-----------|
| **3F** | `payables.get_payables_dashboard`, `payables.get_payment_planning` |
| **3G** | `purchase.get_purchase_dashboard`, `purchase.get_open_purchase_orders` |

**Then:** backfill `executive.payables`, `executive.purchasing`.

**Mobile modules:** `payables`, `purchase`

---

### Wave 5 — 3C Customer 360

| Endpoint | Purpose |
|----------|---------|
| `erp_analysis.customer_360.get_customer_360` | Compose: profile, AR snapshot, recent invoices, open SO, statement link |

**Reuse:**

- `receivables.get_customer_statement`
- `receivables.get_receivables_snapshot` (scoped to customer)
- Wave 3 open SO (if enabled)

**Mobile module:** `customer_360` (or extend existing receivables tab — product decision)

---

### Wave 6 — 3H / 3I / 3J / 3K (mostly extend existing)

| Phase | Action |
|-------|--------|
| **3H Inventory** | Already have `inventory.*`; add `get_stock_cover` if missing; register in `KNOWN_API_METHODS` |
| **3I Profitability** | `profitability.get_gross_profit_dashboard` delegating to `services/kpi/gross_profit.py` + item/territory breakdown |
| **3J Exceptions** | `exceptions.get_management_exceptions` — rule types: overdue_ar, stale_so, low_stock, pending_approval (**no** target_miss) |
| **3K Approval analytics** | `approval_analytics.get_approval_summary` — counts by doctype/state/aging; keep `get_all_approvals` as inbox |

---

## v1 → Phase 3 endpoint map

| v1 (keep) | Phase 3 (add) |
|-----------|---------------|
| `dashboard.get_complete_dashboard_data` | `executive.get_executive_dashboard` |
| `sales_kpis.get_dashboard_kpis` | shared `services/kpi/*` |
| `receivables.*` | `collection.*` (actuals) + `customer_360.*` |
| `inventory.*` | + `get_stock_cover` if needed |
| `approvals.get_all_approvals` | + `approval_analytics.*` |
| — | `sales_orders.*`, `payables.*`, `purchase.*`, `sales_performance.*`, `exceptions.*`, `profitability.*` |

---

## `get_mobile_config` rollout

Add module flags **only when mobile screen + Access Registry exist**:

| Module key | Phase | Default |
|------------|-------|---------|
| `executive` | 3A | `False` until mobile ships |
| `collection` | 3D | `False` |
| `sales_performance` | 3B′ | `False` |
| `sales_orders` | 3E | `False` |
| `payables` | 3F | `False` |
| `purchase` | 3G | `False` |
| `customer_360` | 3C | `False` |
| `profitability` | 3I | `False` |
| `exceptions` | 3J | `False` |
| `approval_analytics` | 3K | `False` |

**Do not add:** `sales_target`, `cash_flow` (deferred per scope).

**Desk:** extend **Mobile App Settings** with new Check fields per wave (or JSON override until fields are added).

---

## Access Object Registry checklist (per endpoint)

For each new `@frappe.whitelist` method:

1. Create registry row: object_type `API`, object_key `erp_analysis.<module>.<method>`
2. Link in **Access Profile Line** for mobile roles
3. Add to `mobile_config.KNOWN_API_METHODS`
4. Document in `ERP_ANALYSIS_API_CONTRACT.md` (v2 section)

---

## SQL / ERPNext dependencies

| KPI | Primary DocTypes |
|-----|------------------|
| Sales | `Sales Invoice` (submitted) |
| Gross profit | `Sales Invoice Item` + COGS from SLE or `base_net_total` − cost fields |
| Collection actuals | `Payment Entry`, `Payment Entry Reference` |
| Receivables | `Payment Ledger Entry` / `Sales Invoice` outstanding |
| Open SO | `Sales Order` (docstatus 1, per_delivered < 100) |
| Open PO | `Purchase Order` |
| Payables | `Purchase Invoice` outstanding |
| Inventory value | `Stock Ledger Entry` / Bin |

**Site variance:** Printechs may use custom fields (Division, Sales Team). Use `dimensions` in Mobile App Settings to hide unsupported breakdowns.

---

## Performance notes

- `get_executive_dashboard` should call services in parallel where possible (`frappe.enqueue` only for async jobs; prefer fast SQL per block).
- Target **&lt; 3s** per block; if slow, split into separate mobile calls gated by `apis.<method>`.
- Cache executive summary 60–120s per `(user, company, date)` if needed (`frappe.cache`).

---

## Testing checklist (per wave)

- [ ] `bench execute erp_analysis.<module>.<method>` with real company
- [ ] Empty site / no data → zeros and `null` blocks, not 500
- [ ] `dimensions.territory: false` → no territory filter in SQL
- [ ] Access Profile denies → 403 or empty per existing pattern
- [ ] `get_mobile_config` reflects new module flag
- [ ] v1 endpoints still pass smoke curl tests

---

## Immediate next steps (Wave 0 + 1 starter)

1. Create `services/kpi/` modules (sales, gross_profit, collection, receivables_summary)
2. Create `executive.py` with `get_executive_dashboard` (null stubs for orders/purchasing/payables)
3. Register `get_executive_dashboard` in `KNOWN_API_METHODS`
4. Add Access Object Registry seed row (manual or patch)
5. Mobile: new screen behind `modules.executive` when ready

---

## Related docs

- [PHASE3_SCOPE.md](../PHASE3_SCOPE.md) — what **not** to build
- [docs/BACKEND_MULTI_CLIENT_GUIDE.md](./BACKEND_MULTI_CLIENT_GUIDE.md) — per-site config
- `ERP_ANALYSIS_API_CONTRACT.md` — mobile contract (add v2 section when Wave 1 ships)
