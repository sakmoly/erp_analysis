"""Non-sales dashboard boards (Receivables Phase 1, Inventory, Collection, Executive)."""

from __future__ import annotations

import json
from typing import Any

OPERATIONS_DASHBOARD_BOARDS: list[dict[str, Any]] = [
	{
		"dashboard_key": "receivables_overview",
		"label": "Receivables",
		"enabled": 1,
		"sort_order": 1,
		"icon_key": "wallet-outline",
	},
]

OPERATIONS_DASHBOARD_MODULES: list[dict[str, Any]] = [
	{
		"module_key": "receivables_overview",
		"label": "Receivables",
		"enabled": 1,
		"sort_order": 860,
		"icon_key": "wallet-outline",
		"route_key": "receivables_overview",
		"screen_type": "dashboard",
		"dashboard_id": "receivables_overview",
		"feature_key": "",
	},
]

OPERATIONS_DASHBOARD_ACCESS_PARENT: dict[str, str] = {
	"receivables_overview": "receivables",
	"collection_overview": "collection",
	"inventory_overview": "inventory",
	"executive_overview": "executive",
}

OPERATIONS_DASHBOARD_MODULE_KEYS: frozenset[str] = frozenset(OPERATIONS_DASHBOARD_ACCESS_PARENT.keys())

DEPRECATED_WIDGET_KEYS = frozenset(
	{
		"receivables_card",
		"receivables_dash_card",
		"recv_dash_total_kpi",
		"recv_dash_overdue_kpi",
		"recv_dash_customers_table",
		"recv_dash_territory_table",
	}
)

PHASE1_DISABLED_WIDGET_KEYS = frozenset(
	{
		"receivables_aging_donut",
		"receivables_territory_donut",
		"receivables_top_customers_table",
		"receivables_territory_table",
	}
)


def _row_config(section: str, group: str, **extra: Any) -> str:
	parts = [
		f'"section_title": "{section}"',
		f'"row_group": "{group}"',
		'"layout": "row"',
		'"columns": 2',
	]
	for key, value in extra.items():
		if isinstance(value, bool):
			parts.append(f'"{key}": {"true" if value else "false"}')
		elif isinstance(value, (int, float)):
			parts.append(f'"{key}": {value}')
		else:
			parts.append(f'"{key}": "{value}"')
	return "{" + ", ".join(parts) + "}"


def _chart_config(**kwargs: Any) -> str:
	return json.dumps(kwargs, separators=(",", ":"))


RECEIVABLES_PHASE1_WIDGETS: list[dict[str, Any]] = [
	{
		"widget_key": "receivables_total_kpi",
		"label": "Total Receivable",
		"widget_type": "KPI",
		"dashboard_id": "receivables_overview",
		"module_key": "receivables",
		"metric_key": "total_receivable",
		"show_currency_symbol": 1,
		"size": "md",
		"config_json": _row_config(
			"Overview",
			"receivables_kpis_r1",
			format="currency_compact",
			kpi_id="total_receivable",
			subtitle="Total outstanding",
		),
		"enabled": 1,
		"sort_order": 10,
	},
	{
		"widget_key": "receivables_overdue_kpi",
		"label": "Overdue",
		"widget_type": "KPI",
		"dashboard_id": "receivables_overview",
		"module_key": "receivables",
		"metric_key": "overdue",
		"show_currency_symbol": 1,
		"size": "md",
		"config_json": _row_config(
			"Overview",
			"receivables_kpis_r1",
			format="currency_compact",
			kpi_id="overdue",
			subtitle="Past due balance",
		),
		"enabled": 1,
		"sort_order": 11,
	},
	{
		"widget_key": "receivables_current_kpi",
		"label": "Not Yet Due",
		"widget_type": "KPI",
		"dashboard_id": "receivables_overview",
		"module_key": "receivables",
		"metric_key": "current",
		"show_currency_symbol": 1,
		"size": "md",
		"config_json": _row_config(
			"Overview",
			"receivables_kpis_r2",
			format="currency_compact",
			kpi_id="current",
			subtitle="Current balance",
		),
		"enabled": 1,
		"sort_order": 12,
	},
	{
		"widget_key": "receivables_overdue_pct_kpi",
		"label": "Overdue %",
		"widget_type": "KPI",
		"dashboard_id": "receivables_overview",
		"module_key": "receivables",
		"metric_key": "overdue_pct",
		"show_currency_symbol": 0,
		"size": "md",
		"config_json": _row_config(
			"Overview",
			"receivables_kpis_r2",
			format="percent",
			kpi_id="overdue_pct",
			subtitle="Share of total receivable",
		),
		"enabled": 1,
		"sort_order": 13,
	},
	{
		"widget_key": "receivables_customer_count_kpi",
		"label": "Customers Owing",
		"widget_type": "KPI",
		"dashboard_id": "receivables_overview",
		"module_key": "receivables",
		"metric_key": "customer_count",
		"show_currency_symbol": 0,
		"size": "md",
		"config_json": _row_config(
			"Overview",
			"receivables_kpis_r3",
			format="integer",
			kpi_id="customer_count",
			subtitle="Customers with balance",
		),
		"enabled": 1,
		"sort_order": 14,
	},
	{
		"widget_key": "receivables_aging_table",
		"label": "Receivables Aging",
		"widget_type": "BAR",
		"dashboard_id": "receivables_overview",
		"module_key": "receivables",
		"metric_key": "outstanding_amount",
		"dimension_key": "aging_bucket",
		"show_currency_symbol": 1,
		"size": "full",
		"config_json": _chart_config(
			payload_source="legacy_chart",
			legacy_method="erp_analysis.receivables.get_receivables_aging_chart",
			chart_key="receivables_aging_buckets_bar",
			dimension="aging_bucket",
			section_title="Receivables Aging (SAR)",
			subtitle="Outstanding by aging bucket",
		),
		"enabled": 1,
		"sort_order": 20,
	},
	{
		"widget_key": "receivables_customer_advances_kpi",
		"label": "Customer Advances",
		"widget_type": "KPI",
		"dashboard_id": "receivables_overview",
		"module_key": "receivables",
		"metric_key": "customer_advances",
		"show_currency_symbol": 1,
		"size": "md",
		"config_json": _chart_config(
			section_title="Overview",
			row_group="receivables_kpis_r3",
			layout="row",
			columns=2,
			format="currency_compact",
			kpi_id="receivables_customer_advances_kpi",
			subtitle="Unallocated customer payments",
			action={
				"type": "navigate",
				"target": "focus_widget",
				"widget_key": "receivables_customer_advances_ranking",
			},
		),
		"enabled": 1,
		"sort_order": 16,
	},
	{
		"widget_key": "receivables_overdue_customers_table",
		"label": "Top Overdue Customers",
		"widget_type": "RANKING",
		"dashboard_id": "receivables_overview",
		"module_key": "receivables",
		"metric_key": "overdue",
		"dimension_key": "customer",
		"show_currency_symbol": 1,
		"size": "full",
		"config_json": _chart_config(
			payload_source="legacy_chart",
			legacy_method="erp_analysis.receivables.get_receivables_overdue_customers_chart",
			chart_key="receivables_overdue_customers",
			dimension="customer",
			row_limit=5,
			section_title="Top Overdue Customers",
			subtitle="Highest overdue balance by customer",
		),
		"enabled": 1,
		"sort_order": 21,
	},
	{
		"widget_key": "receivables_customer_advances_ranking",
		"label": "Top Advances by Customer",
		"widget_type": "RANKING",
		"dashboard_id": "receivables_overview",
		"module_key": "receivables",
		"metric_key": "advance_by_customer",
		"dimension_key": "customer",
		"show_currency_symbol": 1,
		"size": "full",
		"config_json": _chart_config(
			payload_source="legacy_chart",
			legacy_method="erp_analysis.collection.get_customer_advances_customers_chart",
			chart_key="customer_advances_customers",
			dimension="customer",
			row_limit=10,
			section_title="Top Advances by Customer",
			subtitle="Unallocated payments by customer",
			drill_path=["customer", "payment_entry"],
			legacy_drill_method="erp_analysis.collection.get_customer_advances",
			columns=[
				{"key": "rank", "label": "#", "flex": 0.4, "align": "left"},
				{"key": "dimension", "label": "Customer", "flex": 1.6, "align": "left"},
				{
					"key": "metric",
					"label": "Advance",
					"format": "currency_compact",
					"flex": 1,
					"align": "right",
				},
			],
		),
		"enabled": 1,
		"sort_order": 22,
	},
	# Kept in profile for Phase 2 — disabled in Phase 1
	{
		"widget_key": "receivables_aging_donut",
		"label": "Aging Breakdown",
		"widget_type": "DONUT",
		"dashboard_id": "receivables_overview",
		"module_key": "receivables",
		"dimension_key": "aging_bucket",
		"size": "full",
		"config_json": _chart_config(
			payload_source="legacy_chart",
			legacy_method="erp_analysis.receivables.get_receivables_aging_chart",
			chart_key="receivables_aging_buckets",
			dimension="aging_bucket",
			section_title="Aging Analysis",
		),
		"enabled": 0,
		"sort_order": 30,
	},
	{
		"widget_key": "receivables_top_customers_table",
		"label": "Top Customers",
		"widget_type": "BAR",
		"dashboard_id": "receivables_overview",
		"module_key": "receivables",
		"metric_key": "outstanding_amount",
		"dimension_key": "customer",
		"show_currency_symbol": 1,
		"size": "full",
		"config_json": _chart_config(
			payload_source="legacy_chart",
			legacy_method="erp_analysis.receivables.get_receivables_top_customers_chart",
			chart_key="receivables_top_customers",
			dimension="customer",
			row_limit=10,
			section_title="Top Customers",
			subtitle="Outstanding balance by customer",
		),
		"enabled": 0,
		"sort_order": 31,
	},
	{
		"widget_key": "receivables_territory_table",
		"label": "Territory Breakdown",
		"widget_type": "BAR",
		"dashboard_id": "receivables_overview",
		"module_key": "receivables",
		"metric_key": "outstanding",
		"dimension_key": "territory",
		"show_currency_symbol": 1,
		"size": "full",
		"config_json": _chart_config(
			payload_source="legacy_chart",
			legacy_method="erp_analysis.receivables.get_receivables_territory_chart",
			chart_key="receivables_territory",
			dimension="territory",
			section_title="Territory Breakdown",
			subtitle="Outstanding by territory",
		),
		"enabled": 0,
		"sort_order": 32,
	},
]

RECEIVABLES_PHASE2_WIDGETS: list[dict[str, Any]] = [
	{
		"widget_key": "receivables_dso_kpi",
		"label": "DSO",
		"widget_type": "KPI",
		"dashboard_id": "receivables_overview",
		"module_key": "receivables",
		"metric_key": "dso",
		"show_currency_symbol": 0,
		"size": "md",
		"config_json": _row_config(
			"Overview",
			"receivables_kpis_r3",
			format="integer",
			kpi_id="dso",
			subtitle="Days sales outstanding",
		),
		"enabled": 1,
		"sort_order": 15,
	},
	{
		"widget_key": "receivables_overdue_trend",
		"label": "Overdue Trend",
		"widget_type": "LINE",
		"dashboard_id": "receivables_overview",
		"module_key": "receivables",
		"metric_key": "overdue",
		"show_currency_symbol": 1,
		"size": "full",
		"config_json": _chart_config(
			payload_source="legacy_chart",
			legacy_method="erp_analysis.receivables.get_receivables_overdue_trend_chart",
			chart_key="receivables_overdue_trend",
			dimension="month",
			compare="ly",
			section_title="Overdue Trend (SAR)",
			subtitle="Monthly overdue vs last year",
		),
		"enabled": 1,
		"sort_order": 30,
	},
	{
		"widget_key": "receivables_collected_mtd_kpi",
		"label": "Collected MTD",
		"widget_type": "KPI",
		"dashboard_id": "receivables_overview",
		"module_key": "collection",
		"metric_key": "collected_mtd",
		"show_currency_symbol": 1,
		"size": "md",
		"config_json": _row_config(
			"Collection Summary",
			"receivables_collection_r1",
			format="currency_compact",
			kpi_id="collected_mtd",
		),
		"enabled": 1,
		"sort_order": 40,
	},
	{
		"widget_key": "receivables_collected_ytd_kpi",
		"label": "Collected YTD",
		"widget_type": "KPI",
		"dashboard_id": "receivables_overview",
		"module_key": "collection",
		"metric_key": "collected_ytd",
		"show_currency_symbol": 1,
		"size": "md",
		"config_json": _row_config(
			"Collection Summary",
			"receivables_collection_r1",
			format="currency_compact",
			kpi_id="collected_ytd",
		),
		"enabled": 1,
		"sort_order": 41,
	},
	{
		"widget_key": "receivables_collection_efficiency_kpi",
		"label": "Collection Efficiency",
		"widget_type": "KPI",
		"dashboard_id": "receivables_overview",
		"module_key": "collection",
		"metric_key": "collection_efficiency",
		"show_currency_symbol": 0,
		"size": "md",
		"config_json": _row_config(
			"Collection Summary",
			"receivables_collection_r2",
			format="percent",
			kpi_id="collection_efficiency",
		),
		"enabled": 1,
		"sort_order": 42,
	},
	{
		"widget_key": "receivables_avg_collection_days_kpi",
		"label": "Avg. Collection Days",
		"widget_type": "KPI",
		"dashboard_id": "receivables_overview",
		"module_key": "collection",
		"metric_key": "avg_collection_days",
		"show_currency_symbol": 0,
		"size": "md",
		"config_json": _row_config(
			"Collection Summary",
			"receivables_collection_r2",
			format="integer",
			kpi_id="avg_collection_days",
		),
		"enabled": 1,
		"sort_order": 43,
	},
	{
		"widget_key": "receivables_attention",
		"label": "Attention Required",
		"widget_type": "LIST",
		"dashboard_id": "receivables_overview",
		"module_key": "receivables",
		"size": "full",
		"config_json": _chart_config(
			payload_source="legacy",
			legacy_method="erp_analysis.receivables.get_receivables_attention",
			section_title="Attention Required",
		),
		"enabled": 1,
		"sort_order": 50,
	},
]

OPERATIONS_DASHBOARD_WIDGETS: list[dict[str, Any]] = (
	list(RECEIVABLES_PHASE1_WIDGETS) + list(RECEIVABLES_PHASE2_WIDGETS)
)

RECEIVABLES_OVERVIEW_BOARD_KEYS: tuple[str, ...] = ("receivables_overview",)
