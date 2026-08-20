# Mobile Dashboards — Server API Spec (erp_analysis)

**Audience:** Backend / BA team (`erp_analysis`)  
**Mobile app:** Printechs Mobile — custom dashboard screens (Home, Sales, Receivables, Inventory)  
**Status:** Mobile wired · requires `get_dashboard_board_data` + `get_dashboard_widget_data` on server

---

## Overview

The mobile app renders **four dedicated dashboard screens**. Each screen loads widget **layout** from bootstrap and widget **data** from a single batch API call. Company comes from Access Profile (not user-selectable). **Territory** is the user-facing scope filter on all dashboards.

| Screen                | Route                                   | `dashboard_id`         |
| --------------------- | --------------------------------------- | ---------------------- |
| Home                  | Home tab                                | `home`                 |
| Sales Dashboard       | `/dashboard-board/sales_overview`       | `sales_overview`       |
| Receivables Dashboard | `/dashboard-board/receivables_overview` | `receivables_overview` |
| Inventory Dashboard   | `/dashboard-board/inventory_overview`   | `inventory_overview`   |

**Do not** use legacy `get_dashboard_kpis`, `get_complete_dashboard_data`, or `get_executive_dashboard` for these screens.

---

## Load flow

```
Login
  └─ get_my_access          → company, view_territories, permissions

App start / profile refresh
  └─ get_mobile_bootstrap   → dashboards[], widget keys, types, Desk config

Dashboard open (every visit + filter change)
  └─ get_dashboard_board_data?dashboard_id=<board>
       └─ (fallback only) get_dashboard_widget_data per missing widget_key

User drill tap (donut slice → table)
  └─ get_dashboard_widget_data?widget_key=…&drill_depth=1&filters=…
```

| Step | Method                      | Sends values? | Purpose                                         |
| ---- | --------------------------- | ------------- | ----------------------------------------------- |
| 1    | `get_my_access`             | No            | Company + territory scope                       |
| 2    | `get_mobile_bootstrap`      | No            | Layout only — keys, types, order, `drill_views` |
| 3    | `get_dashboard_board_data`  | **Yes**       | All root widget payloads in one batch           |
| 4    | `get_dashboard_widget_data` | **Yes**       | Missing widgets + drill-down only               |

Pull-to-refresh: call board API with `refresh=1`.

---

## Required endpoints

| Method                                       | HTTP                | Auth   | Purpose                         |
| -------------------------------------------- | ------------------- | ------ | ------------------------------- |
| `erp_analysis.api.get_my_access`             | GET / POST          | Bearer | Access Profile scope            |
| `erp_analysis.api.get_mobile_bootstrap`      | GET                 | Bearer | Modules + dashboard layout      |
| `erp_analysis.api.get_mobile_config`         | GET                 | Bearer | Fallback when bootstrap missing |
| `erp_analysis.api.get_dashboard_board_data`  | POST (GET fallback) | Bearer | **Batch** widget data           |
| `erp_analysis.api.get_dashboard_widget_data` | POST (GET fallback) | Bearer | **Single** widget + drill       |

Full paths:

```text
/api/method/erp_analysis.api.get_my_access
/api/method/erp_analysis.api.get_mobile_bootstrap
/api/method/erp_analysis.api.get_dashboard_board_data
/api/method/erp_analysis.api.get_dashboard_widget_data
```

---

## Access scope (`get_my_access`)

Territory filter options and company are derived from Access Profile — not from bootstrap.

```json
{
  "scope": {
    "user": "user@example.com",
    "company": "Printechs Advanced Printing Trading Co.",
    "view_territories": ["Riyadh", "Jeddah", "Dammam"],
    "territories": ["Riyadh", "Jeddah", "Dammam"],
    "allow_view_all_sales": 1,
    "allow_view_all_stock": 1,
    "allow_all_receivable": 0
  }
}
```

| Field                              | Used for                                        |
| ---------------------------------- | ----------------------------------------------- |
| `company`                          | Always sent on board/widget API calls           |
| `view_territories` / `territories` | Territory picker options                        |
| `allow_view_all_sales`             | When set, mobile may show extra territory chips |

---

## Common request parameters

### `get_dashboard_board_data`

| Param          | Required | Example                      | Notes                                            |
| -------------- | -------- | ---------------------------- | ------------------------------------------------ |
| `dashboard_id` | **Yes**  | `home`, `sales_overview`, …  | Board key (see tables below)                     |
| `company`      | **Yes**  | From Access Profile          | Batch is skipped until company is known          |
| `from_date`    | No       | `2026-01-01`                 | `YYYY-MM-DD`                                     |
| `to_date`      | No       | `2026-08-18`                 | `YYYY-MM-DD`                                     |
| `period`       | No       | `ytd`, `mtd`, `qtd`, `today` | Preset id                                        |
| `filters`      | No       | `{"territory":["Jeddah"]}`   | JSON **string**; omit for all territories        |
| `territory`    | No       | `Jeddah`                     | Legacy single-param fallback (mobile sends both) |
| `refresh`      | No       | `1`                          | Bypass server cache on pull-to-refresh           |

**Period presets mobile sends:** `ytd` (default), `mtd`, `qtd`, `today`, `yesterday`, `previous_month`, `previous_year`.

### `get_dashboard_widget_data`

| Param                              | Required | Example                    | Notes                                           |
| ---------------------------------- | -------- | -------------------------- | ----------------------------------------------- |
| `widget_key`                       | **Yes**  | `sales_trend_line`         | Must match bootstrap / catalog key              |
| `company`                          | **Yes**  | From Access Profile        |                                                 |
| `from_date` / `to_date` / `period` | No       | Same as board              |                                                 |
| `filters`                          | No       | `{"territory":["Jeddah"]}` | JSON string                                     |
| `show_ly`                          | No       | `1`                        | Mobile sends `1` when “Last Year” compare is on |
| `drill_depth`                      | No       | `0`, `1`, `2`              | Increment on each drill step                    |
| `limit`                            | No       | `10`                       | Table / ranking row cap                         |

---

## Territory filtering

| User selection                       | Mobile sends                                                  |
| ------------------------------------ | ------------------------------------------------------------- |
| **All Territories**                  | No `filters`, no `territory` param                            |
| **Specific territory** (e.g. Jeddah) | `filters={"territory":["Jeddah"]}` **and** `territory=Jeddah` |

Server must honour `filters.territory[]` on **both** batch and single-widget calls. When filters are omitted, return data for the user's full view scope (respecting Access Profile).

Use **logical keys only** in filters — never ERPNext physical field names (`custom_*`).

Allowed logical filter keys include: `territory`, `warehouse`, `brand`, `division`, `department`, `category`, …

---

## Batch response shape

```json
{
  "message": {
    "dashboard_id": "sales_overview",
    "currency": "SAR",
    "widgets": {
      "sales_total_kpi": {
        "widget_key": "sales_total_kpi",
        "widget_type": "KPI",
        "label": "Total Sales (SAR)",
        "show_ly": true,
        "kpis": [
          {
            "value": 16044275.65,
            "previous": 22560945.66,
            "change_pct": -28.88,
            "format": "currency_compact"
          }
        ]
      },
      "sales_trend_line": {
        "widget_type": "LINE",
        "show_ly": true,
        "chart": {
          "series": [
            { "label": "Jan", "value": 1200000, "value_ly": 980000 },
            { "label": "Feb", "value": 1350000, "value_ly": 1100000 }
          ],
          "summary": {
            "value": 16044275.65,
            "value_ly": 22560945.66,
            "change_pct": -28.88
          }
        }
      }
    },
    "errors": {
      "some_widget_key": "PermissionError: ..."
    },
    "meta": { "widget_count": 14 }
  }
}
```

**Rules**

- `widgets` is an **object keyed by `widget_key`**, not an array.
- Partial failures in `errors` must **not** block other widgets from rendering.
- Empty / null sections are OK — mobile hides empty widgets.

---

## Widget payload by type

Render by **type / `render_hint` / `drill_views`** — never hardcode by widget key.

| `widget_type`       | Data path                          | Mobile UI                            |
| ------------------- | ---------------------------------- | ------------------------------------ |
| `KPI`               | `kpi` or `kpis[]`                  | KPI card / health gauge              |
| `LINE`              | `chart.series[]`                   | Trend chart (This Year vs Last Year) |
| `DONUT` / `PIE`     | `chart.series[]`                   | Donut chart                          |
| `BAR`               | `chart.series[]` or `rows[]`       | Horizontal bar (aging)               |
| `RANKING` / `TABLE` | `table.columns[]` + `table.rows[]` | Ranking / table list                 |
| `LIST`              | `rows[]` or `table.rows[]`         | Alerts, insights, activities         |
| `LINK`              | `action`                           | Navigation tile                      |

### KPI fields

```json
{
  "widget_type": "KPI",
  "show_ly": true,
  "kpis": [
    {
      "value": 1234567.89,
      "previous": 1100000.0,
      "change_pct": 12.2,
      "format": "currency_compact",
      "label": "Total Sales"
    }
  ]
}
```

Alias shapes also accepted: top-level `kpi` object, or `value` / `value_ly` / `change_pct` at root.

### Chart fields (LINE / DONUT / BAR)

```json
{
  "widget_type": "LINE",
  "show_ly": true,
  "chart": {
    "series": [
      {
        "label": "Jan",
        "value": 1200000,
        "value_ly": 980000,
        "change_pct": 22.4,
        "dimension_value": "2026-01"
      }
    ],
    "summary": {
      "value": 16044275.65,
      "value_ly": 22560945.66,
      "change_pct": -28.88
    },
    "compare": "ly"
  }
}
```

For **This Year vs Last Year** trend charts, always include `value_ly` on each series point when `show_ly=1`.

### Table / ranking fields

```json
{
  "widget_type": "RANKING",
  "table": {
    "columns": [
      { "key": "label", "label": "Customer", "flex": 2 },
      {
        "key": "value",
        "label": "Outstanding",
        "format": "currency_compact",
        "align": "right"
      }
    ],
    "rows": [{ "label": "ACME Corp", "value": 125000, "meta": { "rank": 1 } }],
    "currency_display": { "show_symbol": false }
  }
}
```

### List fields (alerts, insights, activities)

```json
{
  "widget_type": "LIST",
  "rows": [
    {
      "label": "3 invoices overdue > 90 days",
      "value": 45000,
      "meta": { "severity": "high", "key": "overdue_90" }
    }
  ]
}
```

### Last Year (LY) comparison

When the user selects **Last Year** on the filter bar, mobile sends `show_ly=1` on widget fetches.

| Widget type   | Required LY fields                               |
| ------------- | ------------------------------------------------ |
| KPI           | `previous` or `value_ly` + optional `change_pct` |
| LINE / BAR    | `value_ly` on each `chart.series[]` point        |
| Chart summary | `chart.summary.value_ly` + `change_pct`          |

Set `show_ly: true` in the response when LY data is included.

### Currency

- Send **raw numbers** only.
- Use column `format`: `currency_compact` → mobile renders `2.28M`.
- Honor `table.currency_display.show_symbol` (default **false** — do not force `SAR` prefix).

---

## Drill-down

Same `widget_key`, increment `drill_depth`, pass accumulated filters:

```http
GET /api/method/erp_analysis.api.get_dashboard_widget_data
  ?widget_key=sales_dash_by_group
  &company=Printechs+Advanced+Printing+Trading+Co.
  &drill_depth=1
  &filters={"territory":["Jeddah"]}
  &show_ly=1
```

Desk config example:

```json
{
  "drill_path": ["territory", "brand"],
  "drill_views": { "0": "donut", "1": "table" },
  "show_ly": true
}
```

| Level | Typical UI      | Payload                        |
| ----- | --------------- | ------------------------------ |
| 0     | Donut / pie     | `chart.series`                 |
| 1     | Table / ranking | `table.columns` + `table.rows` |

---

## Bootstrap requirement (`get_mobile_bootstrap`)

Bootstrap provides **layout only** — no KPI values or chart series.

Each board must appear under `dashboards[]` with matching `key`:

```json
{
  "schema_version": 2,
  "context": {
    "company": "Printechs Advanced Printing Trading Co.",
    "profile": "PRINTECHS-B2B",
    "business_type": "B2B"
  },
  "dashboards": [
    {
      "key": "home",
      "title": "Home Dashboard",
      "widgets": [
        {
          "key": "home_total_sales_kpi",
          "label": "Total Sales (SAR)",
          "type": "KPI",
          "sort_order": 10,
          "config": { "show_ly": true }
        },
        {
          "key": "home_trend_overview",
          "label": "Trend Overview (SAR)",
          "type": "LINE",
          "sort_order": 150,
          "config": { "compare": "ly" }
        }
      ]
    },
    {
      "key": "sales_overview",
      "title": "Sales Dashboard",
      "widgets": []
    },
    {
      "key": "receivables_overview",
      "title": "Receivables Dashboard",
      "widgets": []
    },
    {
      "key": "inventory_overview",
      "title": "Inventory Dashboard",
      "widgets": []
    }
  ]
}
```

More menu modules that open a dashboard screen:

```json
{
  "key": "sales_overview",
  "label": "Sales Overview",
  "enabled": true,
  "screen_type": "dashboard",
  "route_key": "sales_overview",
  "config": { "dashboard_id": "sales_overview" }
}
```

Widget keys in bootstrap should match (or alias) the canonical keys in the tables below.

---

## Board: Home (`dashboard_id: home`)

| Widget key                     | Aliases (optional)                                  | Type | UI section        |
| ------------------------------ | --------------------------------------------------- | ---- | ----------------- |
| `home_total_sales_kpi`         | `total_sales_kpi`, `sales_ytd_kpi`, `net_sales_kpi` | KPI  | Business Overview |
| `home_total_receivables_kpi`   | `total_receivables_kpi`, `receivables_total_kpi`    | KPI  | Business Overview |
| `home_total_inventory_kpi`     | `total_inventory_kpi`, `inventory_value_kpi`        | KPI  | Business Overview |
| `home_total_purchases_kpi`     | `total_purchases_kpi`, `purchases_ytd_kpi`          | KPI  | Business Overview |
| `home_total_payables_kpi`      | `total_payables_kpi`, `payables_total_kpi`          | KPI  | Business Overview |
| `home_gross_profit_kpi`        | `gross_profit_kpi`, `gp_ytd_kpi`                    | KPI  | Business Overview |
| `home_gp_margin_kpi`           | `gp_margin_kpi`, `gross_profit_margin_kpi`          | KPI  | Key Indicators    |
| `home_current_ratio_kpi`       | `current_ratio_kpi`                                 | KPI  | Key Indicators    |
| `home_operating_cash_flow_kpi` | `operating_cash_flow_kpi`, `cash_flow_kpi`          | KPI  | Key Indicators    |
| `home_net_profit_kpi`          | `net_profit_kpi`                                    | KPI  | Key Indicators    |
| `home_sales_health`            | `sales_performance_health`, `sales_health_score`    | KPI  | Health gauge      |
| `home_receivables_health`      | `receivables_health_score`                          | KPI  | Health gauge      |
| `home_inventory_health`        | `inventory_health_score`                            | KPI  | Health gauge      |
| `home_payables_health`         | `payables_health_score`                             | KPI  | Health gauge      |
| `home_trend_overview`          | `trend_overview`, `business_trend`                  | LINE | Multi-line trend  |
| `home_quick_insights`          | `quick_insights`, `home_insights`                   | LIST | Quick Insights    |
| `home_recent_activities`       | `recent_activities`, `activity_feed`                | LIST | Recent Activities |

---

## Board: Sales (`dashboard_id: sales_overview`)

| Widget key                   | Aliases (optional)                           | Type    | UI section           |
| ---------------------------- | -------------------------------------------- | ------- | -------------------- |
| `sales_total_kpi`            | `sales_dash_net_ytd_kpi`, `net_sales_kpi`    | KPI     | Overview KPIs        |
| `sales_orders_kpi`           | `total_orders_kpi`, `total_invoices_kpi`     | KPI     | Overview KPIs        |
| `sales_gp_kpi`               | `gross_profit_kpi`, `sales_gross_profit_kpi` | KPI     | Overview KPIs        |
| `sales_gp_margin_kpi`        | `gross_profit_margin_kpi`, `gp_margin_kpi`   | KPI     | Overview KPIs        |
| `sales_active_customers_kpi` | `active_customers_kpi`, `customer_count_kpi` | KPI     | Overview KPIs        |
| `sales_returns_kpi`          | `returns_kpi`, `sales_return_kpi`            | KPI     | Overview KPIs        |
| `sales_trend_line`           | `sales_overview_trend`, `sales_trend_chart`  | LINE    | Sales Trend          |
| `sales_by_salesperson`       | `top_salespersons`, `salesperson_ranking`    | RANKING | Sales By (tab)       |
| `sales_by_territory`         | `sales_dash_territory`, `territory_ranking`  | RANKING | Sales By (tab)       |
| `sales_by_customer_group`    | `customer_group_ranking`                     | RANKING | Sales By (tab)       |
| `sales_by_channel`           | `channel_ranking`, `sales_channel_ranking`   | RANKING | Sales By (tab)       |
| `sales_donut_customer_group` | `sales_by_customer_group_pie`                | DONUT   | Summary donuts       |
| `sales_dash_by_group`        | `sales_by_group`, `product_group_donut`      | DONUT   | Summary donuts       |
| `sales_donut_channel`        | `sales_by_channel_pie`, `channel_donut`      | DONUT   | Summary donuts       |
| `sales_management_attention` | `sales_attention`, `management_attention`    | LIST    | Management Attention |

---

## Board: Receivables (`dashboard_id: receivables_overview`)

| Widget key                              | Aliases (optional)                           | Type    | UI section               |
| --------------------------------------- | -------------------------------------------- | ------- | ------------------------ |
| `receivables_total_kpi`                 | `total_receivable`                           | KPI     | Overview                 |
| `receivables_overdue_kpi`               | `overdue`                                    | KPI     | Overview                 |
| `receivables_current_kpi`               | `current`, `not_yet_due`                     | KPI     | Overview                 |
| `receivables_overdue_pct_kpi`           | `overdue_pct`                                | KPI     | Overview                 |
| `receivables_customer_count_kpi`        | `customer_count`, `customers_owing`          | KPI     | Overview                 |
| `receivables_dso_kpi`                   | `dso`                                        | KPI     | Overview                 |
| `receivables_aging_buckets_bar`         | `receivables_aging_table`, `aging`           | BAR     | Aging bar                |
| `receivables_overdue_trend`             | `overdue_trend`                              | LINE    | Overdue Trend (TY vs LY) |
| `receivables_collected_mtd_kpi`         | `collected_mtd`                              | KPI     | Collection Summary       |
| `receivables_collected_ytd_kpi`         | `collected_ytd`                              | KPI     | Collection Summary       |
| `receivables_collection_efficiency_kpi` | `collection_efficiency`                      | KPI     | Collection Summary       |
| `receivables_avg_collection_days_kpi`   | `avg_collection_days`                        | KPI     | Collection Summary       |
| `receivables_overdue_customers_table`   | `overdue_customers`, `top_overdue_customers` | RANKING | Top 5 Overdue            |
| `receivables_attention`                 | `attention_required`, `attention`            | LIST    | Attention Required       |

---

## Board: Inventory (`dashboard_id: inventory_overview`)

| Widget key                      | Aliases (optional)                                 | Type    | UI section        |
| ------------------------------- | -------------------------------------------------- | ------- | ----------------- |
| `inventory_total_value_kpi`     | `total_inventory_value_kpi`, `stock_value_kpi`     | KPI     | Overview KPIs     |
| `inventory_stock_qty_kpi`       | `total_stock_quantity_kpi`, `stock_quantity_kpi`   | KPI     | Overview KPIs     |
| `inventory_available_value_kpi` | `available_stock_value_kpi`                        | KPI     | Overview KPIs     |
| `inventory_reserved_value_kpi`  | `reserved_stock_value_kpi`                         | KPI     | Overview KPIs     |
| `inventory_turnover_kpi`        | `inventory_turnover_ytd_kpi`, `turnover_kpi`       | KPI     | Overview KPIs     |
| `inventory_days_kpi`            | `days_of_inventory_kpi`, `inventory_doi_kpi`       | KPI     | Overview KPIs     |
| `inventory_value_trend`         | `inventory_trend_line`, `stock_value_trend`        | LINE    | Value Trend       |
| `inventory_by_warehouse`        | `inventory_warehouse_donut`, `stock_by_warehouse`  | DONUT   | By Warehouse      |
| `inventory_movement_insights`   | `movement_insights`, `stock_movement`              | LIST    | Movement Insights |
| `inventory_aging_bar`           | `inventory_aging`, `stock_aging`                   | BAR     | Aging             |
| `inventory_stock_cover`         | `stock_cover`, `stock_cover_donut`                 | DONUT   | Stock Cover       |
| `inventory_health`              | `inventory_health_score`, `inventory_health_gauge` | KPI     | Health gauge      |
| `inventory_top_items`           | `top_items_by_value`, `top_inventory_items`        | RANKING | Top 5 Items       |
| `inventory_alerts`              | `inventory_alert_list`, `stock_alerts`             | LIST    | Alerts            |

> **Note:** The legacy Inventory Snapshot screen (`/inventory-dashboard`) uses a separate hierarchy API — see [`INVENTORY_BY_TERRITORY_API.md`](./INVENTORY_BY_TERRITORY_API.md). The **Inventory Dashboard** above uses the standard board/widget APIs only.

---

## Example requests

### Batch — Sales Overview, Jeddah, YTD

```bash
curl -s -X POST "https://<site>/api/method/erp_analysis.api.get_dashboard_board_data" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "dashboard_id": "sales_overview",
    "company": "Printechs Advanced Printing Trading Co.",
    "from_date": "2026-01-01",
    "to_date": "2026-08-18",
    "period": "ytd",
    "filters": "{\"territory\":[\"Jeddah\"]}",
    "territory": "Jeddah"
  }'
```

### Batch — Home, all territories, pull-to-refresh

```bash
curl -s -G "https://<site>/api/method/erp_analysis.api.get_dashboard_board_data" \
  -H "Authorization: Bearer <token>" \
  --data-urlencode "dashboard_id=home" \
  --data-urlencode "company=Printechs Advanced Printing Trading Co." \
  --data-urlencode "period=ytd" \
  --data-urlencode "from_date=2026-01-01" \
  --data-urlencode "to_date=2026-08-18" \
  --data-urlencode "refresh=1"
```

### Single widget — drill + LY

```bash
curl -s -G "https://<site>/api/method/erp_analysis.api.get_dashboard_widget_data" \
  -H "Authorization: Bearer <token>" \
  --data-urlencode "widget_key=sales_dash_by_group" \
  --data-urlencode "company=Printechs Advanced Printing Trading Co." \
  --data-urlencode "drill_depth=1" \
  --data-urlencode 'filters={"territory":["Jeddah"]}' \
  --data-urlencode "show_ly=1"
```

### Fallback — missing widget from batch

If `inventory_health` is absent from the batch response, mobile calls:

```bash
curl -s -G "https://<site>/api/method/erp_analysis.api.get_dashboard_widget_data" \
  -H "Authorization: Bearer <token>" \
  --data-urlencode "widget_key=inventory_health" \
  --data-urlencode "company=Printechs Advanced Printing Trading Co." \
  --data-urlencode "period=ytd" \
  --data-urlencode 'filters={"territory":["Riyadh"]}' \
  --data-urlencode "show_ly=1"
```

---

## Server deploy checklist

1. [ ] `get_dashboard_board_data` and `get_dashboard_widget_data` whitelisted and deployed.
2. [ ] All four `dashboard_id` values registered in Mobile App Profile: `home`, `sales_overview`, `receivables_overview`, `inventory_overview`.
3. [ ] Widget keys in bootstrap match canonical keys (or aliases) in the tables above.
4. [ ] Batch returns `widgets` as a **keyed object**, not an array.
5. [ ] Territory filter: honour `filters={"territory":["…"]}` on batch + widget calls.
6. [ ] LY comparison: return `value_ly` / `previous` when `show_ly=1`.
7. [ ] `get_my_access` returns `company` and `view_territories`.
8. [ ] Partial widget errors returned in `errors` map — do not fail the whole board.
9. [ ] Smoke: open each dashboard → one batch call; change territory → batch refetch; pull refresh → `refresh=1`.

---

## Error handling

| Case                       | Expected server behaviour                | Mobile behaviour               |
| -------------------------- | ---------------------------------------- | ------------------------------ |
| Widget permission denied   | Entry in `errors` map                    | Other widgets still render     |
| Board method missing (404) | —                                        | Falls back to per-widget fetch |
| Empty widget data          | Omit key or return empty `kpis`/`series` | Widget hidden                  |
| Invalid territory filter   | Empty data or 403                        | Shows empty state              |
| 401 Unauthorized           | Standard Frappe auth error               | Logout → login screen          |

---

## Related docs

| Document                                                               | Content                                            |
| ---------------------------------------------------------------------- | -------------------------------------------------- |
| [`MOBILE_DASHBOARD_CONTRACT.md`](./MOBILE_DASHBOARD_CONTRACT.md)       | General board contract, drill rules, auth          |
| [`MOBILE_BOOTSTRAP_LAYOUT_JSON.md`](./MOBILE_BOOTSTRAP_LAYOUT_JSON.md) | Bootstrap JSON schema (modules, widgets)           |
| [`MOBILE_SALES_DASHBOARD_TEST.md`](./MOBILE_SALES_DASHBOARD_TEST.md)   | Sales board smoke tests + bench commands           |
| [`ERP_ANALYSIS_API_CONTRACT.md`](./ERP_ANALYSIS_API_CONTRACT.md)       | Full erp_analysis API reference                    |
| [`INVENTORY_BY_TERRITORY_API.md`](./INVENTORY_BY_TERRITORY_API.md)     | Separate inventory hierarchy API (Snapshot screen) |
| [`TABLE_COLUMN_LAYOUT.md`](./TABLE_COLUMN_LAYOUT.md)                   | Table column width / format spec                   |

---

## Mobile implementation map

| Concern                          | Location                                                            |
| -------------------------------- | ------------------------------------------------------------------- |
| Batch API client                 | `src/api/dashboardBoardData.ts`                                     |
| Single widget API client         | `src/api/dashboardWidgetData.ts`                                    |
| Board React Query hook           | `src/hooks/useDashboardBoardData.ts`                                |
| Territory filter + company scope | `src/hooks/useDashboardScope.ts`, `src/utils/dashboardTerritory.ts` |
| Shared filter bar                | `src/components/dashboard/DashboardFilterBar.tsx`                   |
| Home screen                      | `src/screens/home/HomeDashboardScreen.tsx`                          |
| Sales screen                     | `src/screens/sales/SalesDashboardScreen.tsx`                        |
| Receivables screen               | `src/screens/receivables/ReceivablesDashboardScreen.tsx`            |
| Inventory screen                 | `src/screens/inventory/InventoryDashboardScreen.tsx`                |
| Widget catalogs (keys + aliases) | `src/screens/*/ *WidgetCatalog.ts`                                  |
