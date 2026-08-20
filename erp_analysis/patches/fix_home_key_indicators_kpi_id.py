"""Ensure home Key Indicators / Health widgets have unique kpi_id + row_group in profile config."""

from __future__ import annotations

import json

import frappe

PROFILE = "PRINTECHS-B2B"

WIDGET_CONFIG_PATCHES: dict[str, dict] = {
	"home_total_sales_kpi": {
		"kpi_id": "home_total_sales_kpi",
		"row_group": "business_overview",
		"layout": "row",
		"columns": 2,
		"compare": "ly",
		"format": "currency_compact",
	},
	"home_total_receivables_kpi": {
		"kpi_id": "home_total_receivables_kpi",
		"row_group": "business_overview",
		"layout": "row",
		"columns": 2,
		"format": "currency_compact",
	},
	"home_total_inventory_kpi": {
		"kpi_id": "home_total_inventory_kpi",
		"row_group": "business_overview",
		"layout": "row",
		"columns": 2,
		"format": "currency_compact",
	},
	"home_total_purchases_kpi": {
		"kpi_id": "home_total_purchases_kpi",
		"row_group": "business_overview",
		"layout": "row",
		"columns": 2,
		"compare": "ly",
		"format": "currency_compact",
	},
	"home_total_payables_kpi": {
		"kpi_id": "home_total_payables_kpi",
		"row_group": "business_overview",
		"layout": "row",
		"columns": 2,
		"format": "currency_compact",
	},
	"home_gross_profit_kpi": {
		"kpi_id": "home_gross_profit_kpi",
		"row_group": "business_overview",
		"layout": "row",
		"columns": 2,
		"compare": "ly",
		"format": "currency_compact",
	},
	"home_gp_margin_kpi": {
		"kpi_id": "home_gp_margin_kpi",
		"row_group": "key_indicators",
		"layout": "row",
		"columns": 2,
	},
	"home_current_ratio_kpi": {
		"kpi_id": "home_current_ratio_kpi",
		"row_group": "key_indicators",
		"layout": "row",
		"columns": 2,
	},
	"home_operating_cash_flow_kpi": {
		"kpi_id": "home_operating_cash_flow_kpi",
		"row_group": "key_indicators",
		"layout": "row",
		"columns": 2,
	},
	"home_net_profit_kpi": {
		"kpi_id": "home_net_profit_kpi",
		"row_group": "key_indicators",
		"layout": "row",
		"columns": 2,
	},
	"home_sales_health": {
		"kpi_id": "home_sales_health",
		"row_group": "health_gauges",
		"render_hint": "gauge",
		"format": "score",
		"max_value": 100,
	},
	"home_receivables_health": {
		"kpi_id": "home_receivables_health",
		"row_group": "health_gauges",
		"render_hint": "gauge",
		"format": "score",
		"max_value": 100,
	},
	"home_inventory_health": {
		"kpi_id": "home_inventory_health",
		"row_group": "health_gauges",
		"render_hint": "gauge",
		"format": "score",
		"max_value": 100,
	},
	"home_payables_health": {
		"kpi_id": "home_payables_health",
		"row_group": "health_gauges",
		"render_hint": "gauge",
		"format": "score",
		"max_value": 100,
	},
	"sales_total_kpi": {"kpi_id": "sales_total_kpi", "row_group": "sales_overview_kpis", "layout": "row", "columns": 2, "compare": "ly"},
	"sales_cogs_kpi": {
		"kpi_id": "sales_cogs_kpi",
		"row_group": "sales_overview_kpis",
		"layout": "row",
		"columns": 2,
		"compare": "ly",
		"format": "currency_compact",
	},
	"sales_gp_kpi": {"kpi_id": "sales_gp_kpi", "row_group": "sales_overview_kpis", "layout": "row", "columns": 2, "compare": "ly"},
	"sales_gp_margin_kpi": {"kpi_id": "sales_gp_margin_kpi", "row_group": "sales_overview_kpis", "layout": "row", "columns": 2, "compare": "ly"},
	"sales_active_customers_kpi": {"kpi_id": "sales_active_customers_kpi", "row_group": "sales_overview_kpis", "layout": "row", "columns": 2, "compare": "ly"},
	"sales_returns_kpi": {"kpi_id": "sales_returns_kpi", "row_group": "sales_overview_kpis", "layout": "row", "columns": 2, "compare": "ly"},
	"sales_trend_line": {"kpi_id": "sales_trend_line", "section_title": "Sales Trend", "compare": "ly"},
}


def execute():
	if not frappe.db.exists("Mobile App Profile", PROFILE):
		return
	for widget_key, patch in WIDGET_CONFIG_PATCHES.items():
		name = frappe.db.get_value(
			"Mobile Dashboard Widget",
			{"parent": PROFILE, "widget_key": widget_key},
			"name",
		)
		if not name:
			continue
		row = frappe.get_doc("Mobile Dashboard Widget", name)
		config = json.loads(row.config_json or "{}") if row.config_json else {}
		config.update(patch)
		# Legacy payload hints are server-only; KPI routing uses metric_key now.
		for legacy_key in ("payload_source", "legacy_method", "value_field"):
			config.pop(legacy_key, None)
		row.config_json = json.dumps(config)
		if patch.get("compare") == "ly":
			row.show_ly = 1
		row.save(ignore_permissions=True)
	frappe.db.commit()
