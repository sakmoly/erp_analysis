"""Sales module dashboard boards (Option 1B) — separate from home dashboard."""

from __future__ import annotations

from typing import Any

SALES_DASHBOARD_BOARDS: list[dict[str, Any]] = [
	{
		"dashboard_key": "sales_overview",
		"label": "Overview",
		"enabled": 1,
		"sort_order": 10,
		"icon_key": "pie-chart-outline",
	},
	{
		"dashboard_key": "sales_performance",
		"label": "Performance",
		"enabled": 1,
		"sort_order": 11,
		"icon_key": "bar-chart-outline",
	},
	{
		"dashboard_key": "sales_trends",
		"label": "Trends",
		"enabled": 1,
		"sort_order": 12,
		"icon_key": "trending-up-outline",
	},
]

_TERRITORY_TABLE_COLUMNS = """[
  {"key": "dimension", "label": "Territory", "flex": 1.4, "align": "left", "min_width": 72},
  {"key": "metric", "label": "Net Sales", "format": "currency_compact", "flex": 1.1, "align": "right", "min_width": 72},
  {"key": "metric_ly", "label": "Net Sales LY", "format": "currency_compact", "flex": 1.3, "align": "right", "min_width": 88},
  {"key": "change_pct", "label": "Δ%", "format": "percent", "width": 56, "align": "right"}
]"""

_RANKING_TABLE_COLUMNS = """[
  {"key": "dimension", "label": "Name", "flex": 1.6, "align": "left", "min_width": 88},
  {"key": "metric", "label": "Net Sales", "format": "currency_compact", "flex": 1.1, "align": "right", "min_width": 72},
  {"key": "metric_ly", "label": "Net Sales LY", "format": "currency_compact", "flex": 1.2, "align": "right", "min_width": 80},
  {"key": "change_pct", "label": "Δ%", "format": "percent", "width": 56, "align": "right"}
]"""

SALES_DASHBOARD_WIDGETS: list[dict[str, Any]] = [
	{
		"widget_key": "sales_dash_net_ytd_kpi",
		"label": "Net Sales",
		"widget_type": "KPI",
		"dashboard_id": "sales_overview",
		"module_key": "sales",
		"metric_key": "net_sales",
		"period": "ytd",
		"show_ly": 1,
		"size": "full",
		"config_json": '{"subtitle": "Year-to-Date vs Last Year", "compare": "ly", "format": "currency_compact", "kpi_id": "sales_dash_net_ytd"}',
		"enabled": 1,
		"sort_order": 10,
	},
	{
		"widget_key": "sales_dash_invoices_ytd_kpi",
		"label": "Total Invoices",
		"widget_type": "KPI",
		"dashboard_id": "sales_overview",
		"module_key": "sales",
		"metric_key": "transactions",
		"period": "ytd",
		"show_ly": 1,
		"size": "full",
		"config_json": '{"compare": "ly", "format": "integer", "kpi_id": "sales_dash_invoices_ytd"}',
		"enabled": 1,
		"sort_order": 11,
	},
	{
		"widget_key": "sales_dash_avg_inv_ytd_kpi",
		"label": "Average Invoice",
		"widget_type": "KPI",
		"dashboard_id": "sales_overview",
		"module_key": "sales",
		"metric_key": "average_transaction",
		"period": "ytd",
		"show_ly": 1,
		"size": "full",
		"config_json": '{"compare": "ly", "format": "currency_compact", "kpi_id": "sales_dash_avg_inv_ytd"}',
		"enabled": 1,
		"sort_order": 12,
	},
	{
		"widget_key": "sales_dash_territory",
		"label": "Sales by Territory",
		"widget_type": "DONUT",
		"dashboard_id": "sales_overview",
		"module_key": "sales",
		"metric_key": "net_sales",
		"dimension_key": "territory",
		"period": "ytd",
		"show_currency_symbol": 0,
		"size": "full",
		"table_columns_json": _TERRITORY_TABLE_COLUMNS,
		"config_json": '{"compare": "ly", "drill_path": ["territory", "brand", "warehouse"], "drill_views": {"0": "donut", "1": "table", "2": "table"}}',
		"enabled": 1,
		"sort_order": 13,
	},
	{
		"widget_key": "sales_dash_link_salespersons",
		"label": "Salespersons",
		"widget_type": "LINK",
		"dashboard_id": "sales_overview",
		"module_key": "sales_performance",
		"config_json": '{"action": {"type": "navigate", "target": "module", "route_key": "sales_performance", "screen": "salespersons"}}',
		"enabled": 1,
		"sort_order": 14,
	},
	{
		"widget_key": "sales_dash_link_products",
		"label": "Products",
		"widget_type": "LINK",
		"dashboard_id": "sales_overview",
		"module_key": "sales",
		"config_json": '{"action": {"type": "navigate", "target": "dashboard", "dashboard_id": "sales_performance", "focus_widget": "sales_dash_by_brand"}}',
		"enabled": 1,
		"sort_order": 15,
	},
	{
		"widget_key": "sales_dash_top_customers",
		"label": "Top Customers",
		"widget_type": "RANKING",
		"dashboard_id": "sales_performance",
		"module_key": "sales",
		"metric_key": "net_sales",
		"dimension_key": "customer",
		"period": "ytd",
		"show_currency_symbol": 0,
		"size": "full",
		"table_columns_json": _RANKING_TABLE_COLUMNS,
		"config_json": '{"compare": "ly", "subtitle": "Year-to-Date ranking"}',
		"enabled": 1,
		"sort_order": 10,
	},
	{
		"widget_key": "sales_dash_by_brand",
		"label": "Sales by Brand",
		"widget_type": "TABLE",
		"dashboard_id": "sales_performance",
		"module_key": "sales",
		"metric_key": "net_sales",
		"dimension_key": "brand",
		"period": "ytd",
		"show_currency_symbol": 0,
		"size": "full",
		"table_columns_json": _RANKING_TABLE_COLUMNS,
		"config_json": '{"compare": "ly", "subtitle": "Year-to-Date by brand"}',
		"enabled": 1,
		"sort_order": 11,
	},
	{
		"widget_key": "sales_dash_group_bar",
		"label": "Sales by Group",
		"widget_type": "BAR",
		"dashboard_id": "sales_trends",
		"module_key": "sales",
		"metric_key": "net_sales",
		"dimension_key": "group",
		"period": "ytd",
		"size": "full",
		"config_json": '{"compare": "ly", "subtitle": "YTD vs last year by group"}',
		"enabled": 1,
		"sort_order": 10,
	},
	{
		"widget_key": "sales_dash_territory_bar",
		"label": "Sales by Territory",
		"widget_type": "BAR",
		"dashboard_id": "sales_trends",
		"module_key": "sales",
		"metric_key": "net_sales",
		"dimension_key": "territory",
		"period": "ytd",
		"size": "full",
		"config_json": '{"compare": "ly", "subtitle": "YTD vs last year by territory"}',
		"enabled": 1,
		"sort_order": 11,
	},
]

SALES_DASHBOARD_TEST_MODULE: dict[str, Any] = {
	"module_key": "sales_overview",
	"label": "Sales Dashboard (Test)",
	"enabled": 1,
	"sort_order": 900,
	"icon_key": "flask-outline",
	"route_key": "sales_overview",
	"screen_type": "dashboard",
	"dashboard_id": "sales_overview",
	"feature_key": "",
}

SALES_DASHBOARD_DEPRECATED_MODULE_KEYS = frozenset({"sales_dashboard_test"})

SALES_DASHBOARD_BOARD_KEYS: tuple[str, ...] = (
	"sales_overview",
	"sales_performance",
	"sales_trends",
)
