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

## 9. v2 migration (dynamic profile-driven home)

**Status:** Backend ready. Mobile app still on v1 until it switches boot + widget loading.

| | v1 (current mobile) | v2 (profile-driven) |
|---|---------------------|---------------------|
| Boot | `get_mobile_config` | `get_mobile_bootstrap` |
| Home layout | `dashboards_json` / hard-coded widget ids | `bootstrap.dashboard[]` from Mobile App Profile |
| Widget data | Fixed API per id (e.g. `sales_card` → `get_dashboard_kpis`) | `get_dashboard_widget_data?widget_key=...` |
| Chart types | Not supported (all `expandable` / list) | `PIE`, `DONUT`, `BAR`, `LINE`, `RANKING` via analytics |
| Desk users | Unaffected | Unaffected (no Access Profile = legacy behavior) |

### Recommended mobile rollout

1. Feature-flag v2 boot for Access Profile users only (e.g. when `bootstrap.context.profile` is set).
2. Replace home widget loop: read `dashboard[]`, call `get_dashboard_widget_data` per `key`.
3. Add renderers for `widget_type` / `meta.render_hint`.
4. Keep v1 path as fallback when bootstrap returns no profile.

### Example v2 home sequence

```
POST /api/method/erp_analysis.api.get_mobile_bootstrap
  → dashboard: [{ key: "sales_card", widget_type: "PIE", ... }, ...]

GET /api/method/erp_analysis.api.get_dashboard_widget_data?widget_key=sales_card&limit=8
  → { chart: { series: [...] }, widget_type: "PIE" }

GET /api/method/erp_analysis.api.get_dashboard_widget_data?widget_key=receivables_card
  → { data: { ... legacy receivables shape ... }, widget_type: "LIST" }
```

### PRINTECHS-B2B test user

Link an Access Profile to **`PRINTECHS-B2B`** manually in Desk. After mobile v2 migration, home should show PIE sales by territory, receivables list, inventory list — as configured in Mobile App Profile.

Load or refresh the profile fixture (does not auto-link users):

```bash
bench --site <site> execute erp_analysis.scripts.load_printechs_b2b_profile.ensure_profile
bench --site <site> execute erp_analysis.scripts.load_printechs_b2b_profile.ensure_profile --kwargs "{'update_existing': True}"
```

---

## 10. Chart drill-down (mobile v2)

### Desk setup (one-time)

On **Mobile App Profile → Dashboard Widgets**, add or edit a chart widget:

| Field | Example |
|-------|---------|
| Widget Key | `sales_by_brand` |
| Widget Type | `PIE` |
| Module Key | `sales` |
| Metric Key | `net_sales` |
| Dimension Key | `brand` |
| Config JSON | see below |

```json
{
  "drill_path": ["brand", "territory", "salesperson"]
}
```

Ensure `brand`, `territory`, and `salesperson` are enabled under **Dimensions** on the same profile.

### Files to add/change in the BA mobile repo

Typical Ionic/React structure — adjust paths to match your project:

| File | Action |
|------|--------|
| `src/services/erpAnalysisApi.ts` | Add `getDashboardWidgetData()` |
| `src/types/mobileBootstrap.ts` | Add widget + drill types |
| `src/components/charts/DrillableChartCard.tsx` | New — pie/bar + tap handler |
| `src/pages/HomeDashboard.tsx` | Load widgets from bootstrap; open drill sheet on tap |

### TypeScript types

```typescript
// src/types/mobileBootstrap.ts

export type DrillFilters = Record<string, string[]>;

export interface DashboardWidgetConfig {
  drill_path?: string[];
  drill_chart_type?: string;
}

export interface DashboardWidget {
  key: string;
  label: string;
  widget_type: string;
  metric_key?: string;
  dimension_key?: string;
  module_key?: string;
  config?: DashboardWidgetConfig;
  config_json?: string;
}

export interface ChartSeriesPoint {
  label: string;
  value: number;
  dimension_value?: string;
}

export interface WidgetChartResponse {
  widget_key: string;
  widget_type: string;
  label: string;
  chart: {
    series: ChartSeriesPoint[];
    metric: string;
    dimension: string;
    filters: DrillFilters;
  };
  meta: {
    drill_path?: string[] | null;
    drill_depth?: number | null;
    next_dimension?: string | null;
    drillable?: boolean;
    render_hint?: string;
  };
}

export interface DrillStackEntry {
  dimension: string;
  label: string;
  value: string;
}
```

### API helper

```typescript
// src/services/erpAnalysisApi.ts

import type { DrillFilters, WidgetChartResponse } from '../types/mobileBootstrap';

const BASE = '/api/method';

export async function getDashboardWidgetData(params: {
  widget_key: string;
  company?: string;
  from_date?: string;
  to_date?: string;
  limit?: number;
  dimension?: string;
  filters?: DrillFilters;
  drill_depth?: number;
}): Promise<WidgetChartResponse> {
  const res = await fetch(`${BASE}/erp_analysis.api.get_dashboard_widget_data`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      ...params,
      filters: params.filters ? JSON.stringify(params.filters) : undefined,
    }),
  });
  const json = await res.json();
  if (json.exc) throw new Error(json.exc);
  return json.message as WidgetChartResponse;
}
```

If your app uses query params + OAuth instead of POST JSON, equivalent GET:

```
/api/method/erp_analysis.api.get_dashboard_widget_data
  ?widget_key=sales_by_brand
  &dimension=territory
  &filters={"brand":["NIKE"]}
```

### Drill state + slice tap handler

```typescript
// src/components/charts/DrillableChartCard.tsx (core logic)

import { useState } from 'react';
import type {
  DashboardWidget,
  DrillFilters,
  DrillStackEntry,
  WidgetChartResponse,
} from '../types/mobileBootstrap';
import { getDashboardWidgetData } from '../services/erpAnalysisApi';

export function useWidgetDrill(widget: DashboardWidget) {
  const [stack, setStack] = useState<DrillStackEntry[]>([]);
  const [filters, setFilters] = useState<DrillFilters>({});
  const [data, setData] = useState<WidgetChartResponse | null>(null);
  const [loading, setLoading] = useState(false);

  const drillPath = widget.config?.drill_path ?? [];
  const currentDimension =
    stack.length > 0
      ? widget.config?.drill_path?.[stack.length] ?? data?.chart.dimension
      : widget.dimension_key;

  async function load(levelFilters: DrillFilters = filters, dimension?: string) {
    setLoading(true);
    try {
      const payload = await getDashboardWidgetData({
        widget_key: widget.key,
        dimension,
        drill_depth: dimension ? undefined : stack.length || undefined,
        filters: levelFilters,
        limit: 10,
      });
      setData(payload);
      setFilters(levelFilters);
    } finally {
      setLoading(false);
    }
  }

  async function onSliceTap(point: { label: string; dimension_value?: string }) {
    const value = point.dimension_value ?? point.label;
    const activeDim = data?.chart.dimension ?? widget.dimension_key;
    if (!activeDim || !data?.meta.drillable || !data.meta.next_dimension) return;

    const nextFilters: DrillFilters = {
      ...filters,
      [activeDim]: [value],
    };
    const nextDim = data.meta.next_dimension;

    setStack((s) => [...s, { dimension: activeDim, label: point.label, value }]);
    await load(nextFilters, nextDim);
  }

  async function goBack() {
    if (stack.length === 0) {
      setFilters({});
      await load({}, widget.dimension_key);
      return;
    }
    const newStack = stack.slice(0, -1);
    const newFilters: DrillFilters = {};
    for (const entry of newStack) {
      newFilters[entry.dimension] = [entry.value];
    }
    const depth = newStack.length;
    const nextDimension = drillPath[depth] ?? widget.dimension_key;
    setStack(newStack);
    await load(newFilters, nextDimension);
  }

  return { data, loading, stack, load, onSliceTap, goBack };
}
```

### Home screen wiring

```typescript
// src/pages/HomeDashboard.tsx (sketch)

// 1. After login: bootstrap = await getMobileBootstrap()
// 2. For each widget in bootstrap.dashboard:
//    - LIST → getDashboardWidgetData({ widget_key }) once, render list
//    - PIE/BAR → render <DrillableChartCard widget={w} /> which calls load() on mount

useEffect(() => {
  load({}, widget.dimension_key); // initial chart
}, [widget.key]);
```

### UX checklist

1. Show breadcrumb from `stack` (e.g. `Brand > NIKE > Territory`).
2. Back button calls `goBack()` — pops one level and refetches.
3. Disable tap when `meta.drillable === false` (leaf level).
4. On 403, show “Outside your territory scope” (filter rejected by server).
5. Keep v1 fallback: if bootstrap has no profile, use existing hard-coded cards.

### Verify from bench

```bash
# Level 0 — all brands
bench --site site1.local execute erp_analysis.api.get_dashboard_widget_data \
  --kwargs "{'widget_key': 'sales_by_brand', 'limit': 5}"

# Level 1 — territories for one brand
bench --site site1.local execute erp_analysis.api.get_dashboard_widget_data \
  --kwargs "{'widget_key': 'sales_by_brand', 'dimension': 'territory', 'filters': '{\"brand\": [\"NIKE\"]}'}"
```

---

## Related

- [MOBILE_PLATFORM_API_V2.md](./MOBILE_PLATFORM_API_V2.md) — v2 bootstrap + dynamic dashboard widget data
- [BACKEND_MULTI_CLIENT_GUIDE.md](./BACKEND_MULTI_CLIENT_GUIDE.md)
- [PHASE3_IMPLEMENTATION_PLAN.md](./PHASE3_IMPLEMENTATION_PLAN.md)
- `erp_analysis/mobile_config.py` — `KNOWN_API_METHODS`, defaults
