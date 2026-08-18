# B2B Phase 1 — Sales Backend Development Specification

**Project:** ERP Analysis  
**Application:** `erp_analysis`  
**Platform:** ERPNext / Frappe v15  
**Phase:** B2B Phase 1 — Sales  
**Target:** Backend only  
**Mobile application changes:** **NONE**

---

## 1. Objective

Extend the existing `erp_analysis` backend into a complete B2B Sales Management Analysis module for senior management.

The existing mobile application is already dynamic. It reads backend configuration, dashboards, widgets, dimensions, and API responses dynamically.

**Therefore:**

> Do not modify the mobile application.  
> Do not create new React Native screens.  
> Do not change the mobile application navigation code.  
> Do not hard-code Sales dashboards in the mobile application.

All new Sales dashboards, KPIs, charts, rankings, tables, filters, and drill-down capabilities must be delivered from the ERPNext backend using the existing dynamic framework.

The backend must remain generic enough to work for different B2B customers with different ERPNext master structures and optional/custom dimensions.

---

# 2. Mandatory First Step — Audit Existing Code

Before writing or changing any code, inspect the entire existing `erp_analysis` application.

At minimum review:

```text
erp_analysis/sales.py
erp_analysis/sales_kpis.py
erp_analysis/sales_performance.py
erp_analysis/sales_orders.py
erp_analysis/profitability.py
erp_analysis/analytics.py
erp_analysis/customer.py
erp_analysis/customer_360.py
erp_analysis/dashboard.py
erp_analysis/executive.py
erp_analysis/mobile_config.py
erp_analysis/access_context.py

erp_analysis/services/
erp_analysis/services/kpi/
erp_analysis/permissions/

erp_analysis/erp_analysis/doctype/mobile_app_profile/
erp_analysis/erp_analysis/doctype/mobile_app_module/
erp_analysis/erp_analysis/doctype/mobile_app_dashboard/
erp_analysis/erp_analysis/doctype/mobile_dashboard_widget/
erp_analysis/erp_analysis/doctype/mobile_analysis_dimension/
erp_analysis/erp_analysis/doctype/access_profile/
```

Also inspect all patches, fixtures, installation logic, smoke tests, and any existing dynamic dashboard/bootstrap API.

### Important rule

**Do not recreate functionality that already exists.**

If an existing method already provides the required data:

1. Reuse it.
2. Extend it only when necessary.
3. Preserve its current response contract where the mobile application already depends on it.
4. Add fields in a backward-compatible manner.
5. Avoid duplicate SQL implementations of the same KPI.

Before coding, produce an internal implementation map showing:

```text
Requirement
→ Existing implementation
→ Reuse / Extend / New
→ File/service to modify
```

Do not ask the user to manually identify this. Inspect the source code.

---

# 3. Existing Dynamic Architecture Must Be Preserved

The application already contains dynamic backend DocTypes including:

```text
Mobile App Profile
Mobile App Module
Mobile App Dashboard
Mobile Dashboard Widget
Mobile Analysis Dimension
```

The current widget types include:

```text
KPI
BAR
LINE
PIE
DONUT
TABLE
RANKING
MATRIX
LIST
LINK
```

Use the existing backend-driven architecture.

The intended flow is:

```text
ERPNext
   ↓
Mobile App Profile
   ↓
Modules / Dashboards / Widgets / Dimensions
   ↓
Dynamic backend API
   ↓
Existing Mobile Application
   ↓
Automatic rendering
```

No mobile source-code modification is permitted in this phase.

---

# 4. B2B Sales Module Structure

The Sales module should provide these management dashboards:

```text
Sales
├── Sales Overview
├── Sales Trend
├── Sales Performance
├── Customer Analysis
├── Product Analysis
├── Order Book
├── Profitability
└── Sales Attention
```

If the current mobile metadata architecture represents these as dashboards, create them using `Mobile App Dashboard` and `Mobile Dashboard Widget`.

If the existing bootstrap/profile service generates configuration differently, follow the existing architecture rather than creating a second configuration mechanism.

Suggested dashboard keys:

```text
sales_overview
sales_trend
sales_performance
sales_customer
sales_product
sales_order_book
sales_profitability
sales_attention
```

All keys must be stable, lowercase, and suitable for API/mobile use.

---

# 5. Global Sales Filters

All Sales analytics must use a common filter structure.

Support wherever applicable:

```text
company
from_date
to_date
period
comparison
territory
territories
branch
division
department
warehouse
sales_person
customer
customer_group
item
item_group
brand
cost_center
```

Do not assume every customer uses every dimension.

Only expose/filter/group a dimension if:

1. It exists in the relevant ERPNext/custom source.
2. It is enabled in the Mobile App Profile / Mobile Analysis Dimension.
3. The logged-in user has permission to access it.

### Period values

Support at least:

```text
today
mtd
qtd
ytd
custom
```

Where useful also support:

```text
yesterday
wtd
last_7_days
last_30_days
last_month
last_quarter
last_year
```

All date calculations must be server-side and deterministic.

---

# 6. Comparison Engine

Management dashboards require comparison, not just absolute amounts.

Support:

```text
previous_period
previous_year
none
```

Examples:

```text
MTD vs previous month same elapsed days
MTD vs same period last year
YTD vs same period last year
Custom period vs equivalent previous period
Custom period vs same dates last year
```

Return at least:

```json
{
  "current": 1250000,
  "comparison": 1100000,
  "variance": 150000,
  "variance_pct": 13.64,
  "direction": "up"
}
```

Handle zero comparison values safely.

Never divide by zero.

If both values are zero:

```text
variance_pct = 0
direction = "flat"
```

If previous is zero and current is positive, do not return a meaningless infinity value.

---

# 7. Sales Calculation Rules

Create one shared calculation policy and use it consistently across all Sales dashboards.

## 7.1 Source documents

Primary actual-sales source:

```text
Sales Invoice
Sales Invoice Item
```

Submitted documents only:

```text
docstatus = 1
```

Canceled and draft documents must not be included.

If the existing `tabSalesDashBoard` dataset/view is the established optimized analytical source, it may continue to be used, but results must reconcile with ERPNext Sales Invoice data.

### Returns

Returns must reduce net sales.

Use ERPNext return semantics and ensure returned values/quantities are correctly negative or otherwise subtracted.

### Currency

Management KPIs must be returned in **company/base currency** unless the endpoint explicitly requests document currency.

Use ERPNext base fields where available.

Do not sum mixed transaction currencies.

---

# 8. Core Sales Measures

Create or standardize these reusable measures:

```text
gross_sales
net_sales
sales_return
discount_amount
discount_pct
qty_sold
invoice_count
customer_count
average_invoice_value
gross_profit
gross_profit_pct
cogs
open_order_value
open_order_count
```

## Definitions

### Gross Sales

Amount before applicable invoice/item discounts according to the source data available.

### Net Sales

The actual recognized sales amount after discounts and returns, excluding taxes unless the established ERP Analysis convention already includes tax.

The entire application must use one definition.

### Sales Returns

Absolute value of returned sales for reporting:

```text
sales_return = positive display value
```

but it must reduce net sales.

### Average Invoice Value

```text
Net Sales / Distinct Submitted Sales Invoices
```

### Gross Profit

```text
Net Sales - COGS
```

### Gross Profit %

```text
Gross Profit / Net Sales × 100
```

If Net Sales = 0, GP % = 0.

---

# 9. Dashboard 1 — Sales Overview

Create a management overview containing KPI widgets and concise charts.

## KPI widgets

Required:

```text
Net Sales
Gross Sales
Sales Returns
Discount Amount
Invoice Count
Average Invoice Value
Quantity Sold
Gross Profit
Gross Profit %
Active Customers
```

Each KPI should support:

```text
current value
comparison value
variance
variance %
direction
```

Example:

```json
{
  "key": "net_sales",
  "label": "Net Sales",
  "value": 1284000,
  "formatted_value": "SAR 1.284M",
  "comparison_value": 1125000,
  "variance": 159000,
  "variance_pct": 14.13,
  "direction": "up"
}
```

Formatting may remain a mobile responsibility if that is the existing contract. Do not introduce formatted strings if the mobile currently expects raw numeric values only.

## Charts

Required:

```text
Daily / Monthly Sales Trend
Sales vs Last Year
Sales by Territory
Sales by Salesperson
Sales by Customer
Sales by Product/Brand
```

Dashboard must be concise. Large rankings should open/drill into their dedicated dashboards instead of returning thousands of rows in the overview.

---

# 10. Dashboard 2 — Sales Trend

Create a reusable Sales Trend service.

Supported grouping:

```text
day
week
month
quarter
year
```

Response example:

```json
{
  "group_by": "month",
  "series": [
    {
      "period": "2026-01",
      "label": "Jan",
      "net_sales": 850000,
      "gross_profit": 220000,
      "gp_pct": 25.88
    }
  ]
}
```

Comparison mode should optionally return:

```text
current series
comparison series
```

Example:

```json
{
  "current": [...],
  "comparison": [...]
}
```

Required trend analyses:

```text
Net Sales Trend
Gross Profit Trend
GP % Trend
Invoice Count Trend
Average Invoice Value Trend
```

---

# 11. Dashboard 3 — Sales Performance

Management must be able to analyze performance by business dimension.

Supported `group_by` values should include enabled/available dimensions such as:

```text
territory
branch
division
department
sales_person
customer
customer_group
item
item_group
brand
warehouse
cost_center
```

Do not hard-code only these fields. Use the existing Mobile Analysis Dimension mechanism where possible.

For every grouped row return:

```text
dimension_key
dimension_value
label
net_sales
comparison_sales
variance
variance_pct
gross_profit
gross_profit_pct
invoice_count
quantity
contribution_pct
rank
```

Example:

```json
{
  "dimension_key": "territory",
  "rows": [
    {
      "value": "Riyadh",
      "label": "Riyadh",
      "net_sales": 4800000,
      "comparison_sales": 4100000,
      "variance": 700000,
      "variance_pct": 17.07,
      "gross_profit": 1392000,
      "gross_profit_pct": 29.0,
      "invoice_count": 418,
      "quantity": 1920,
      "contribution_pct": 37.38,
      "rank": 1
    }
  ]
}
```

### Ranking

Support:

```text
top
bottom
```

and parameters:

```text
limit
offset/page
sort_by
sort_order
```

Never load all customers/items for initial dashboard display.

---

# 12. Salesperson Analysis

Existing salesperson ranking/performance functionality should be reused and standardized.

Required analysis:

```text
Salesperson Sales
LY / Previous Period Sales
Growth %
Gross Profit
GP %
Invoice Count
Customer Count
Average Invoice
Contribution %
Rank
```

Drill-down:

```text
Salesperson
  ↓
Customers
  ↓
Invoices
  ↓
Invoice Items
```

Where ERPNext invoices contain multiple Sales Team rows, respect the existing allocation/percentage logic.

Do not double count invoices.

---

# 13. Dashboard 4 — Customer Analysis

This is a critical B2B management dashboard.

Required sections:

```text
Top Customers
Bottom/Declining Customers
New Customers
Inactive Customers
Lost Customers
Customer Contribution
Customer Profitability
Customer Sales Growth
Customer Purchase Frequency
```

## Customer performance row

Return:

```text
customer
customer_name
customer_group
territory
sales
comparison_sales
growth_pct
gross_profit
gp_pct
invoice_count
average_invoice
last_invoice_date
days_since_last_sale
contribution_pct
```

Where possible also include:

```text
outstanding
overdue
credit_limit
credit_utilisation_pct
open_order_value
```

These may be obtained from existing Customer 360/Receivables/Order Book services instead of duplicating calculations.

---

# 14. New Customers

Definition should be configurable, but default:

> A customer with Sales activity during the selected period whose first-ever submitted Sales Invoice falls within the selected period.

Return:

```text
customer
customer_name
first_invoice_date
first_invoice
period_sales
invoice_count
sales_person
territory
```

Avoid incorrectly classifying a customer as new simply because they had no sales in the immediately preceding period.

---

# 15. Inactive Customers

Provide configurable inactivity thresholds.

Default options:

```text
30 days
60 days
90 days
180 days
365 days
```

Definition:

> Customer had historical sales but no submitted sales invoice within the selected inactivity threshold.

Return:

```text
customer
customer_name
last_invoice_date
days_inactive
last_invoice_value
last_12m_sales
sales_person
territory
```

---

# 16. Lost / Declining Customers

## Declining Customers

Compare current selected period against the equivalent comparison period.

Allow thresholds such as:

```text
sales decrease > 10%
sales decrease > 25%
sales decrease > 50%
```

Return:

```text
current_sales
comparison_sales
decline_amount
decline_pct
```

## Lost Customers

Default definition:

> Customer had sales in the comparison period but zero sales in the current equivalent period.

Return:

```text
customer
comparison_sales
last_invoice_date
sales_person
territory
```

Ensure this is clearly different from general inactivity.

---

# 17. Customer Contribution / Concentration Risk

Calculate customer contribution:

```text
Customer Sales / Total Sales × 100
```

Provide:

```text
Top 5 customer contribution %
Top 10 customer contribution %
Top 20 customer contribution %
```

This helps management identify concentration risk.

Example response:

```json
{
  "top_5_pct": 42.3,
  "top_10_pct": 58.4,
  "top_20_pct": 72.1
}
```

---

# 18. Customer 360 Integration

Do not replace the existing Customer 360 module.

The Sales Customer dashboard must drill into/reuse Customer 360.

Customer 360 should ultimately provide or link to:

```text
YTD Sales
Previous Year Sales
Growth
Gross Profit
GP %
Outstanding
Overdue
Credit Limit
Credit Utilisation
Open Sales Orders
Recent Invoices
Recent Collections
Product Mix
Sales Trend
```

Where these already exist, only connect/reuse them.

---

# 19. Dashboard 5 — Product Analysis

Required grouping:

```text
item
item_group
brand
division
```

and dynamically any supported item-level analysis dimensions.

Metrics:

```text
net_sales
quantity
gross_profit
gross_profit_pct
comparison_sales
growth_pct
contribution_pct
invoice_count
customer_count
rank
```

Required lists:

```text
Top Selling Products by Value
Top Selling Products by Quantity
Top Gross Profit Products
Low Margin Products
Declining Products
Products with Sales Last Year but No Sales Current Period
```

Where inventory information is necessary, do not duplicate Inventory calculations during Phase 1 unless needed for a lightweight cross-reference.

---

# 20. Product Mix / Contribution

Return contribution percentages by:

```text
Brand
Item Group
Division
Item
```

Example:

```json
{
  "rows": [
    {
      "brand": "Hitachi",
      "sales": 2850000,
      "contribution_pct": 31.4
    }
  ]
}
```

Support Pareto analysis:

```text
Top contributors representing approximately 80% of Sales
```

Return cumulative contribution percentage per ranked row.

---

# 21. Dashboard 6 — Order Book

Reuse and extend existing:

```text
sales_orders.py
services/sales_orders.py
```

Required KPIs:

```text
Open Sales Order Count
Open Sales Order Value
Pending Delivery Count
Pending Delivery Value
Partially Delivered Count
Overdue Order Count
Overdue Order Value
Pending Billing Value
```

Required analyses:

```text
Open Orders by Customer
Open Orders by Territory
Open Orders by Salesperson
Open Orders by Item/Brand
Open Orders by Expected Delivery Month
Overdue Orders
```

## Remaining order value

Use remaining/undelivered/unbilled values correctly.

Do not report original order total as open value after partial fulfillment.

---

# 22. Sales Order Aging

Provide order aging buckets based on order date and/or promised delivery date.

Suggested:

```text
0–7 days
8–15 days
16–30 days
31–60 days
60+ days
```

Also classify:

```text
Not Due
Due Today
Overdue
```

Drill-down:

```text
Order Aging
  ↓
Customer
  ↓
Sales Order
  ↓
Sales Order Items
```

---

# 23. Dashboard 7 — Profitability

Reuse:

```text
profitability.py
services/profitability.py
services/kpi/gross_profit.py
```

Do not build a parallel gross-profit engine.

Required KPIs:

```text
Net Sales
COGS
Gross Profit
GP %
```

Analyze by:

```text
Customer
Salesperson
Territory
Branch
Division
Brand
Item Group
Item
```

Required management lists:

```text
Highest GP Customers
Lowest GP Customers
Highest GP Products
Low Margin Sales
Negative Margin Sales
High Sales / Low Margin
Margin Decline vs Comparison Period
```

---

# 24. Margin Erosion

Create analysis to detect deterioration in profitability.

For each supported group:

```text
current_sales
current_gp
current_gp_pct
comparison_sales
comparison_gp
comparison_gp_pct
gp_pct_change
```

Example:

```text
Customer ABC
Previous GP %: 31%
Current GP %: 23%
Margin erosion: -8 percentage points
```

Return percentage-point change separately from percentage change.

Use:

```text
gp_pct_point_change = current_gp_pct - comparison_gp_pct
```

---

# 25. Discount Analysis

Management should be able to identify excessive discounting.

Where ERPNext data allows, provide:

```text
Total Discount Amount
Average Discount %
Top Discounted Customers
Top Discounted Salespersons
Top Discounted Items
Invoices Above Discount Threshold
```

Allow configurable thresholds:

```text
5%
10%
15%
20%
```

Do not infer discounts incorrectly from tax-inclusive vs tax-exclusive values.

---

# 26. Dashboard 8 — Sales Attention

Create an exception-oriented Sales management dashboard.

Possible alerts:

```text
Sales Down vs LY
Major Customer Sales Decline
Lost Customer
Negative Margin Invoice
Low Margin Customer
High Discount Invoice
Overdue Sales Order
Large Open Order
Order Without Delivery Progress
Customer Over Credit Limit with New Open Orders
```

Reuse Receivables data for credit warnings if available.

Do not duplicate AR business logic.

Each attention row should contain:

```text
severity
type
title
description
entity_type
entity_name
value
reference_doctype
reference_name
drilldown
```

Suggested severities:

```text
critical
warning
info
```

---

# 27. Generic Drill-Down Framework

Every chart/table should support navigation into deeper detail without mobile code changes wherever the current widget/config framework supports metadata.

Desired chains:

## Sales

```text
Sales
→ Territory
→ Salesperson
→ Customer
→ Sales Invoice
→ Sales Invoice Item
```

## Customer

```text
Customer
→ Invoice
→ Invoice Item
```

## Product

```text
Brand
→ Item Group
→ Item
→ Customer
→ Invoice
```

## Order Book

```text
Order Book
→ Customer
→ Sales Order
→ Sales Order Item
```

Implement drill-down using generic backend metadata/config wherever possible.

Do not create a unique mobile-specific route implementation for every chart.

---

# 28. Recommended Generic Sales Analysis API

If the existing `analytics.py`, `services/analytics_sales.py`, and dimension services can safely be extended, prefer a generic method.

Example conceptual endpoint:

```python
get_sales_analysis(
    company=None,
    from_date=None,
    to_date=None,
    period=None,
    comparison=None,
    group_by=None,
    secondary_group_by=None,
    metric=None,
    filters=None,
    sort_by=None,
    sort_order=None,
    limit=None,
    offset=None
)
```

Possible metrics:

```text
net_sales
gross_sales
quantity
gross_profit
gross_profit_pct
invoice_count
average_invoice
customer_count
discount
returns
```

Possible grouping:

```text
territory
branch
division
sales_person
customer
customer_group
item
item_group
brand
warehouse
month
```

However:

> Do not create this API if the existing analytics service already provides equivalent generic functionality.

Extend existing code instead.

---

# 29. API Response Standard

Use a predictable envelope compatible with the existing mobile client.

If the existing app has an established response contract, preserve it.

For new generic endpoints, preferred structure:

```json
{
  "success": true,
  "meta": {
    "company": "Company A",
    "from_date": "2026-01-01",
    "to_date": "2026-08-17",
    "period": "ytd",
    "comparison": "previous_year",
    "currency": "SAR",
    "group_by": "territory",
    "generated_at": "2026-08-17T15:00:00"
  },
  "kpis": {},
  "rows": [],
  "total_count": 0,
  "has_more": false
}
```

Do not force this envelope onto existing methods if it would break the current mobile app.

Backward compatibility has priority.

---

# 30. Dynamic Widget Configuration

Register Sales dashboards and widgets in the existing backend dynamic configuration.

Do not rely on manually entering JSON into Desk as the only installation path.

The module should be installable/updateable consistently.

Use one of the existing accepted mechanisms:

```text
install hook
patch
fixture
bootstrap/default configuration
idempotent setup method
```

whichever matches the current project architecture.

### Idempotency

Running setup multiple times must not create duplicate:

```text
Mobile App Module
Mobile App Dashboard
Mobile Dashboard Widget
Mobile Analysis Dimension
```

records.

Update matching stable keys instead.

---

# 31. Suggested Sales Dashboard Metadata

Create/ensure module:

```text
module_key: sales
label: Sales
enabled: 1
screen_type: dashboard
```

Suggested dashboards:

```text
sales_overview
sales_trend
sales_performance
sales_customer
sales_product
sales_order_book
sales_profitability
sales_attention
```

Suggested widget examples:

```text
sales_net_sales
sales_gross_profit
sales_gp_pct
sales_invoice_count
sales_avg_invoice
sales_returns
sales_discount
sales_trend_monthly
sales_by_territory
sales_by_salesperson
sales_top_customers
sales_top_products
sales_open_orders
sales_customer_decline
sales_margin_erosion
sales_attention_list
```

Use existing `widget_type` values only unless there is a genuine backend reason to add a new generic widget type.

---

# 32. Dynamic Dimensions

Use `Mobile Analysis Dimension`.

For B2B default dimensions consider:

```text
company
territory
branch
division
department
sales_person
customer
customer_group
warehouse
item
item_group
brand
cost_center
```

Some customers may use custom fields such as:

```text
business_unit
product_division
market_segment
principal
sales_channel
project
```

The backend architecture must allow these to be added through metadata/configuration without mobile development.

Do not hard-code a customer-specific custom field into generic Sales SQL unless it is mapped through the dimension framework.

---

# 33. Access Control / Security

Every whitelisted Sales endpoint must use the existing access guard.

Review and follow:

```text
erp_analysis/access_context.py
erp_analysis/permissions/
Access Profile
Access Profile Territory
```

At minimum enforce:

```text
authenticated user
company scope
territory/view scope
module permission
profile access
```

Where applicable enforce branch/other enabled dimension scope.

Never trust `company`, `territory`, `customer`, or arbitrary filter values from the client without applying backend authorization.

### SQL security

All dynamic SQL values must be parameterized.

Dynamic field/table identifiers must be selected only from a validated allowlist/registered dimension definition.

Never directly concatenate raw client-supplied `group_by`, `sort_by`, fieldname, table name, or condition into SQL.

---

# 34. ERPNext Permissions

Backend access must not bypass ERPNext business permissions unnecessarily.

For document-level drill-down:

```text
Sales Invoice
Sales Order
Customer
```

respect Frappe permission checks wherever appropriate.

Analytical aggregation may use controlled SQL for performance, but it must still enforce the application's scope rules.

---

# 35. Performance Requirements

Management dashboards must remain fast with large B2B datasets.

Target:

```text
Overview API: ideally < 2 seconds
Ranking/chart API: ideally < 3 seconds
Large drill-down table: paginated
```

Do not execute one SQL query per row.

Avoid N+1 database access.

Use aggregated SQL/query builder or optimized services.

### Pagination

Detailed customer/item/invoice tables must support:

```text
limit
offset
```

or page/page_size.

Recommended maximum default:

```text
20–50 rows
```

Maximum request size should be bounded.

---

# 36. Caching

Use caching only where safe.

Possible short cache for:

```text
management overview
rankings
trend charts
```

Cache key must include all relevant factors:

```text
user/access scope
company
dates
filters
dimension
comparison
```

Never return cached data belonging to a different user's scope.

If the existing widget batch cache framework is suitable, reuse it.

---

# 37. SalesDashBoard Compatibility

Existing code references:

```text
tabSalesDashBoard
```

Do not remove or rename this dependency without first determining its current purpose.

If it is a materialized/custom analytical table/view:

1. Document all source columns.
2. Confirm reconciliation against Sales Invoice.
3. Add fallback logic only if necessary.
4. Avoid silently returning inconsistent numbers between endpoints.

A single Sales KPI displayed in different dashboards must return the same value when using the same filters and period.

Example:

```text
Sales Overview Net Sales
=
Executive Dashboard Sales
=
Sales Trend total
=
Sales Performance grouped total
```

Allow only explainable rounding differences.

---

# 38. Data Reconciliation

Add automated reconciliation tests for:

```text
Net Sales
Invoice Count
Sales Returns
Gross Profit
Open Sales Order Value
```

At least compare backend aggregate results against direct ERPNext document queries for known test periods.

Test:

```text
no data
single invoice
multiple invoices
return invoice
discount
multiple territories
multiple salespersons
partial sales order delivery
cancelled invoice
cancelled order
```

---

# 39. Testing Requirements

Create or extend backend automated tests.

Recommended files:

```text
tests/test_sales_overview.py
tests/test_sales_analysis.py
tests/test_sales_customers.py
tests/test_sales_products.py
tests/test_sales_orders.py
tests/test_sales_profitability.py
tests/test_sales_permissions.py
tests/test_sales_dynamic_config.py
```

Follow the repository's existing test layout if different.

## Functional tests

Verify:

```text
MTD
QTD
YTD
Custom range
Previous-period comparison
Previous-year comparison
Returns
Discount
GP
Grouping
Ranking
Pagination
Drill-down
```

## Security tests

Verify user cannot:

```text
request unauthorized company
request unauthorized territory
bypass scope with comma-separated territories
inject SQL through group_by
inject SQL through sort_by
inject SQL through dimension filters
```

---

# 40. Smoke Test

Extend the existing `smoke_test.py` or equivalent.

The Sales Phase 1 smoke test should call at least:

```text
Sales Overview
Sales Trend
Salesperson Ranking
Product Ranking
Customer Analysis
Order Book
Profitability
Sales Attention
Dynamic Mobile Configuration
```

Expected:

```text
HTTP / RPC succeeds
response is valid JSON
no traceback
no permission leakage
numeric fields are numeric
empty datasets return [] / 0 cleanly
```

---

# 41. Error Handling

Management dashboards should not crash the complete application because one optional dimension is unavailable.

For optional analysis:

```text
missing custom dimension
missing optional source field
empty data
```

return an empty/disabled section where appropriate.

But do not hide real programming/database errors silently.

Use:

```python
frappe.log_error(...)
```

with meaningful titles.

Avoid broad `except Exception: return []` unless the existing project intentionally uses safe degradation and logging.

---

# 42. Logging

Add useful backend logging for unexpected failures but avoid excessive logs for successful requests.

Never log:

```text
passwords
API tokens
authorization headers
session cookies
sensitive customer data unnecessarily
```

---

# 43. Backward Compatibility

This phase must not break:

```text
existing mobile app
existing API endpoint names
existing dashboards
Receivables
Inventory
Approvals
Catalogue
Executive Dashboard
Purchase
Payables
Customer 360
```

Existing API methods listed in mobile configuration must continue to function.

If an endpoint must be superseded:

1. Keep the old method as a wrapper.
2. Route internally to the new service.
3. Preserve the old response structure.

---

# 44. No Mobile Changes

This is a strict acceptance condition.

Cursor must **not modify**:

```text
React Native
Expo
Android
iOS
mobile UI source
mobile routes
mobile components
mobile state management
mobile API client
```

The only backend-related `mobile_*` files that may be modified are ERPNext backend configuration/services required to publish dynamic modules, dashboards, widgets, dimensions, or API metadata.

---

# 45. No Hard-Coded Client-Specific Logic

This application will eventually be used for multiple customers and later Retail/Fashion customers.

Phase 1 is B2B, but code must remain reusable.

Bad:

```python
if company == "Printechs":
    use_brand = True
```

Good:

```text
Mobile App Profile
→ Business Type = B2B
→ enabled dimensions
→ configured field mapping
```

Do not use company names to control business logic.

---

# 46. B2B Profile

Where the existing profile engine supports it, ensure a B2B profile can enable the Sales module with appropriate dashboards.

Business type:

```text
B2B
```

Default B2B Sales dimensions may include:

```text
Company
Territory
Branch
Division
Department
Salesperson
Customer
Customer Group
Warehouse
Brand
Item Group
Item
```

The profile determines which are visible.

---

# 47. Suggested Backend Service Structure

Do not reorganize unnecessarily, but prefer keeping RPC/controller methods thin and business logic in services.

Suggested conceptual organization:

```text
erp_analysis/
    sales.py
    sales_kpis.py
    sales_performance.py
    sales_orders.py
    profitability.py
    analytics.py

    services/
        sales_overview.py
        sales_trends.py
        sales_analysis.py
        sales_customers.py
        sales_products.py
        sales_attention.py
        sales_orders.py
        profitability.py

        kpi/
            sales.py
            gross_profit.py
```

Only add files that improve maintainability.

Do not split working code just to match this proposed tree.

---

# 48. Common Utility Layer

Avoid repeating:

```text
date period resolution
comparison period resolution
scope resolution
dimension validation
percentage change
pagination
currency metadata
SQL condition generation
```

Create/reuse shared helpers.

Prefer one source of truth.

---

# 49. Recommended New/Extended Public APIs

After auditing the existing methods, expose the minimum necessary public API.

Conceptually required capabilities:

```text
get_sales_dashboard
get_sales_overview
get_sales_trends
get_sales_analysis
get_sales_customer_analysis
get_sales_product_analysis
get_sales_attention

get_salesperson_ranking
get_salesperson_performance
get_product_ranking
get_product_performance

get_order_book_dashboard
get_open_sales_orders

get_gross_profit_dashboard
get_profitability_dashboard

get_customer_360
```

Do **not** blindly create all of these names if current equivalent endpoints exist.

The goal is capability, not endpoint proliferation.

---

# 50. Batch Dashboard Loading

If the current dynamic mobile framework supports loading multiple widgets in one backend request, use it.

Avoid a home/dashboard screen making 20 independent requests.

Preferred:

```text
dashboard metadata
+
widget keys
+
one/batched data request
```

where practical.

Reuse `mobile_widgets`, `widget_batch_cache`, or related existing services if they already solve this problem.

---

# 51. Widget Metric Registry

Where possible, create or extend a server-side registry that maps a safe metric key to an implementation.

Concept:

```python
SALES_METRICS = {
    "net_sales": ...,
    "gross_sales": ...,
    "gross_profit": ...,
    "gross_profit_pct": ...,
    "invoice_count": ...,
    "average_invoice": ...,
    "sales_return": ...,
}
```

The client sends:

```text
metric_key = net_sales
```

not arbitrary SQL.

Likewise dimension keys must resolve through a safe registry.

---

# 52. Management Insights

After the core numerical dashboards work, create simple deterministic insights.

Examples:

```text
Sales are 14.2% above the same YTD period last year.
Riyadh contributes 37.4% of total sales.
Top 5 customers contribute 42.3% of sales.
Customer ABC sales decreased 38% vs last year.
Brand XYZ GP% dropped from 31% to 23%.
SAR 840K of open orders are overdue.
```

These must be computed from backend data.

Do not use an external AI service.

Return structured insights:

```json
{
  "severity": "warning",
  "type": "customer_decline",
  "title": "Customer sales decline",
  "message": "ABC sales decreased 38% versus the comparison period.",
  "entity": "ABC"
}
```

---

# 53. Data Quality Flags

If important source data is missing, provide backend data-quality warnings where possible.

Examples:

```text
Salesperson missing on invoices
Territory missing on customers/invoices
Brand missing on items
COGS unavailable
Custom dimension mapping invalid
```

Do not silently categorize all missing values as valid business categories without identifying them.

For grouping, use a consistent label such as:

```text
Unassigned
```

when appropriate.

---

# 54. Final Sales Dashboard Acceptance Criteria

Phase 1 is complete only when management can answer all of these from the backend-driven mobile application without mobile code changes:

### Overall

```text
How much did we sell?
Are we growing?
What is our GP and GP%?
How many invoices/customers?
What are returns and discounts?
```

### Where

```text
Which territory is performing best?
Which branch/division is growing?
Which area is declining?
```

### Who

```text
Who are the top salespersons?
Who is declining?
Which customers contribute most?
Which customers are lost/inactive?
```

### What

```text
Which products/brands sell most?
Which products generate most GP?
Which products have margin erosion?
```

### Orders

```text
What is our open order book?
Which orders are overdue?
Which customers have the largest pending orders?
```

### Profitability

```text
Which customers are profitable?
Which products are low margin?
Where is margin declining?
Are any invoices negative margin?
```

### Attention

```text
What needs management attention today?
```

---

# 55. Implementation Sequence

Implement in this order.

## Step 1 — Audit and Reconciliation

```text
Review current code
Map existing APIs/services
Confirm Sales calculation rules
Reconcile current KPIs
```

## Step 2 — Shared Sales Core

```text
date resolver
comparison resolver
metric calculations
dimension resolver
scope enforcement
pagination
```

## Step 3 — Sales Overview

```text
KPIs
trend
basic rankings
```

## Step 4 — Sales Performance

```text
salesperson
territory
branch/division
dynamic dimensions
```

## Step 5 — Customer Analysis

```text
top
growth
decline
new
inactive
lost
concentration
```

## Step 6 — Product Analysis

```text
item
item group
brand
contribution
growth
```

## Step 7 — Order Book

```text
open
pending
partial
overdue
aging
```

## Step 8 — Profitability

```text
GP
GP%
margin erosion
negative/low margin
```

## Step 9 — Sales Attention

```text
exception engine
structured management alerts
```

## Step 10 — Dynamic Backend Configuration

```text
B2B Sales dashboards
widgets
dimensions
stable keys
```

## Step 11 — Tests

```text
functional
reconciliation
security
performance
smoke test
```

---

# 56. Deployment Requirements

After implementation:

```bash
bench --site <site-name> migrate
bench --site <site-name> clear-cache
bench restart
```

If the project uses supervisor/systemd production commands, follow the existing server deployment standard.

Do not run destructive database commands.

Do not reset existing customer configuration.

All patches/setup scripts must be safe to run on an existing production database.

---

# 57. Git Requirements

Before modifying code:

```bash
git status
git branch --show-current
git remote -v
```

Create a dedicated branch, for example:

```bash
git checkout -b feature/b2b-sales-phase1
```

Commit in logical units.

Suggested commits:

```text
feat: standardize b2b sales metrics and comparison engine
feat: add dynamic sales performance analysis
feat: add b2b customer sales analytics
feat: add product contribution analytics
feat: extend sales order book analytics
feat: add margin erosion and sales attention
feat: register b2b sales dashboard metadata
test: add b2b sales backend coverage
```

Do not commit:

```text
__pycache__
*.pyc
logs
secrets
site_config.json
API keys
tokens
private backups
```

---

# 58. Deliverables

At completion provide:

## A. Source changes

All backend code required for B2B Sales Phase 1.

## B. Migration/setup

Any patch/setup required to create/update:

```text
Mobile App Module
Mobile App Dashboard
Mobile Dashboard Widget
Mobile Analysis Dimension
```

## C. Tests

Automated backend tests and smoke-test coverage.

## D. Documentation

Create:

```text
B2B_PHASE_1_SALES_IMPLEMENTATION_NOTES.md
```

containing:

```text
Files changed
Files added
Existing APIs reused
New APIs added
Calculation definitions
Dashboard keys
Widget keys
Dimension keys
Testing performed
Known limitations
Deployment commands
```

## E. API verification

Provide sample `bench execute`, curl, or authenticated API tests for the implemented public methods.

---

# 59. Cursor Working Rules

Cursor must follow these rules throughout the implementation:

1. **Inspect before editing.**
2. **Do not modify the mobile application.**
3. **Preserve backward compatibility.**
4. **Reuse current services before writing duplicate code.**
5. **Keep RPC endpoints thin.**
6. **Put reusable business logic in services.**
7. **Use parameterized SQL.**
8. **Validate all dynamic dimensions and sorting keys against allowlists/config.**
9. **Apply existing access-profile and territory scope to every analytical query.**
10. **Do not hard-code Printechs or any customer name.**
11. **Do not hard-code optional custom ERPNext fields.**
12. **Use B2B profile/dimension metadata.**
13. **Return numeric values as numbers.**
14. **Return clean zeros/empty arrays when there is genuinely no data.**
15. **Log unexpected failures.**
16. **Do not silently hide permission errors.**
17. **Avoid N+1 queries.**
18. **Paginate large results.**
19. **Use stable dashboard/widget keys.**
20. **Make setup/migrations idempotent.**
21. **Run tests before completion.**
22. **Do not declare completion if calculations have not been reconciled.**

---

# 60. Final Verification Checklist

Before marking Phase 1 complete, confirm all items below.

- [ ] Existing mobile app code has not been changed.
- [ ] Sales module loads from backend configuration.
- [ ] Sales Overview is available.
- [ ] MTD/QTD/YTD/custom periods work.
- [ ] Previous-year comparison works.
- [ ] Previous-period comparison works.
- [ ] Net Sales reconciles with ERPNext.
- [ ] Returns are correctly handled.
- [ ] Canceled documents are excluded.
- [ ] Gross Profit reconciles.
- [ ] GP % is correct.
- [ ] Territory analysis works.
- [ ] Salesperson analysis works.
- [ ] Customer analysis works.
- [ ] Product/brand analysis works.
- [ ] New customers are calculated correctly.
- [ ] Inactive customers work.
- [ ] Lost customers work.
- [ ] Declining customers work.
- [ ] Customer concentration works.
- [ ] Open Sales Orders reconcile.
- [ ] Partial deliveries are correctly reflected.
- [ ] Overdue orders are identified.
- [ ] Margin erosion works.
- [ ] Negative/low-margin analysis works.
- [ ] Discount analysis works where source data permits.
- [ ] Sales Attention returns meaningful exceptions.
- [ ] Drill-down APIs work.
- [ ] Pagination works.
- [ ] Dynamic dimensions are validated securely.
- [ ] User territory/company access cannot be bypassed.
- [ ] Dashboard/widget setup is idempotent.
- [ ] Existing Receivable/Inventory/etc. functionality still works.
- [ ] Automated tests pass.
- [ ] Smoke tests pass.
- [ ] Implementation notes are created.

---

# 61. Important Scope Boundary

This file covers **B2B Sales Phase 1 only**.

Do not start implementing the following as part of this phase except where existing data is reused for Sales context:

```text
Inventory Phase
Receivables Phase
Purchase Phase
Payables Phase
Retail/Fashion analysis
POS analysis
Store/hour/cashier/tender analysis
Retail promotion analytics
Fashion Style/Color/Size/Season analysis
```

Those will be separate phases.

The Sales backend, however, must be designed so these modules can later integrate cleanly into the same dynamic management-analysis application.

---

# 62. End Goal

When this phase is complete, the existing dynamic mobile application should automatically become a strong B2B Sales Management BI application simply because the ERPNext backend now publishes richer dashboards, widgets, metrics, dimensions, drill-down metadata, and secured data.

The architecture should remain:

```text
ONE MOBILE APPLICATION

        ↓

DYNAMIC BACKEND

        ↓

B2B PROFILE TODAY
RETAIL PROFILE LATER
FASHION PROFILE LATER
SUPERMARKET PROFILE LATER
```

**No application rebuild should be necessary when a new backend dashboard or supported analysis dimension is introduced.**
