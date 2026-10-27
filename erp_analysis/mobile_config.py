"""Mobile app config defaults and merge logic for get_mobile_config."""

from __future__ import annotations

import json
from typing import Any

import frappe

from erp_analysis import __version__ as APP_VERSION

MODULE_FIELDS = {
	"sales": "module_sales",
	"receivables": "module_receivables",
	"inventory": "module_inventory",
	"approvals": "module_approvals",
	"catalogue": "module_catalogue",
	"push": "module_push",
	"settings": "module_settings",
	# Phase 3
	"executive": "module_executive",
	"collection": "module_collection",
	"sales_performance": "module_sales_performance",
	"sales_orders": "module_sales_orders",
	"payables": "module_payables",
	"purchase": "module_purchase",
	"customer_360": "module_customer_360",
	"profitability": "module_profitability",
	"exceptions": "module_exceptions",
	"approval_analytics": "module_approval_analytics",
}

DIMENSION_FIELDS = {
	"company": "dimension_company",
	"territory": "dimension_territory",
	"warehouse": "dimension_warehouse",
	"brand": "dimension_brand",
	"division": "dimension_division",
	"department": "dimension_department",
	"cost_center": "dimension_cost_center",
	"branch": "dimension_branch",
}

# Documented API method short names (mobile reads apis.<name> === false to skip).
KNOWN_API_METHODS = (
	"get_complete_dashboard_data",
	"get_executive_dashboard",
	"get_collection_dashboard",
	"get_collection_attention",
	"get_collection_payments",
	"get_customer_advances",
	"get_customer_advances_customers_chart",
	"get_salesperson_ranking",
	"get_salesperson_performance",
	"get_product_ranking",
	"get_product_performance",
	"get_sales_by_division_drill",
	"get_item_stock_by_code",
	"get_item_sales_qty",
	"get_order_book_dashboard",
	"get_open_sales_orders",
	"get_payables_dashboard",
	"get_payment_planning",
	"get_purchase_dashboard",
	"get_open_purchase_orders",
	"get_customer_360",
	"get_customer",
	"search_customers",
	"get_stock_cover",
	"get_inventory_health",
	"get_dead_stock",
	"get_gross_profit_dashboard",
	"get_profitability_dashboard",
	"get_management_exceptions",
	"get_approval_summary",
	"get_approval_analytics",
	"get_sales_order_dashboard",
	"get_dashboard_kpis",
	"get_sales_dashboard",
	"get_receivables_snapshot",
	"get_receivables_performance",
	"get_receivables_trends",
	"get_receivables_dashboard",
	"get_receivables_aging_chart",
	"get_receivables_territory_chart",
	"get_receivables_top_customers_chart",
	"get_receivables_overdue_customers_chart",
	"get_receivables_overdue_trend_chart",
	"get_receivables_attention",
	"get_territory_receivables",
	"get_territory_receivables_list",
	"get_customer_statement",
	"get_inventory_snapshot",
	"get_inventory_performance",
	"get_inventory_trends",
	"get_inventory_risk",
	"get_inventory_hierarchy",
	"get_inventory_items",
	"get_all_approvals",
	"approve_document",
	"reject_document",
	"get_complete_employees_data",
	"get_employee_profile",
	"get_employees",
	"get_catalogues_list",
	"get_catalogue_pages",
	"get_catalogue_flip_url",
	"send_statement_pdf",
	"get_statement_pdf",
	"get_statement_branding",
)

DEFAULT_DASHBOARDS = [
	{
		"id": "home",
		"title": "Dashboard",
		"module": "sales",
		"widgets": [
			{"id": "sales_card", "type": "expandable", "title": "Sales Performance"},
			{"id": "receivables_card", "type": "expandable", "title": "Receivables"},
			{"id": "inventory_card", "type": "expandable", "title": "Inventory"},
		],
	},
]

# Optional Phase 3 home layout (paste into Mobile App Settings → Dashboards JSON).
PHASE3_DASHBOARDS_EXAMPLE = [
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
			{"id": "exceptions_card", "type": "expandable", "title": "Exceptions", "module": "exceptions"},
		],
	},
]


def default_modules() -> dict[str, bool]:
	return {
		"sales": True,
		"receivables": True,
		"inventory": True,
		"approvals": True,
		"catalogue": True,
		"push": True,
		"settings": True,
		# Phase 3 — all enabled by default (override per site in Mobile App Settings)
		"executive": True,
		"collection": True,
		"sales_performance": True,
		"sales_orders": True,
		"payables": True,
		"purchase": True,
		"customer_360": True,
		"profitability": True,
		"exceptions": True,
		"approval_analytics": True,
	}


def default_dimensions() -> dict[str, bool]:
	return {
		"company": True,
		"territory": True,
		"warehouse": True,
		"brand": True,
		"division": True,
		"department": True,
		"cost_center": False,
		"branch": True,
	}


def get_default_mobile_config() -> dict[str, Any]:
	return {
		"app": "erp_analysis",
		"version": APP_VERSION,
		"modules": default_modules(),
		"dimensions": default_dimensions(),
		"apis": {},
		"dashboards": DEFAULT_DASHBOARDS,
	}


def parse_disabled_api_methods(raw: str | None) -> list[str]:
	if not raw:
		return []
	methods = []
	for part in raw.replace("\n", ",").split(","):
		name = part.strip()
		if name:
			methods.append(name)
	return methods


def _single_field_is_set(doctype: str, fieldname: str) -> bool:
	"""True when a Singles DocType field was explicitly saved in tabSingles."""
	return bool(
		frappe.db.sql(
			"""
			SELECT 1 FROM tabSingles
			WHERE doctype = %s AND field = %s
			LIMIT 1
			""",
			(doctype, fieldname),
		)
	)


def build_mobile_config() -> dict[str, Any]:
	config = get_default_mobile_config()

	if not frappe.db.exists("DocType", "Mobile App Settings"):
		return config

	try:
		settings = frappe.get_single("Mobile App Settings")
	except Exception:
		return config

	for key, fieldname in MODULE_FIELDS.items():
		if not settings.meta.has_field(fieldname):
			continue
		# Only override code defaults when Desk explicitly saved the checkbox.
		# Unset Check fields otherwise read as 0 and wrongly disable modules.
		if _single_field_is_set("Mobile App Settings", fieldname):
			config["modules"][key] = bool(settings.get(fieldname))

	for key, fieldname in DIMENSION_FIELDS.items():
		if not settings.meta.has_field(fieldname):
			continue
		if _single_field_is_set("Mobile App Settings", fieldname):
			config["dimensions"][key] = bool(settings.get(fieldname))

	disabled = parse_disabled_api_methods(settings.get("disabled_api_methods"))
	for method in disabled:
		config["apis"][method] = False

	raw_dashboards = (settings.get("dashboards_json") or "").strip()
	if raw_dashboards:
		try:
			parsed = json.loads(raw_dashboards)
			if isinstance(parsed, list):
				config["dashboards"] = parsed
		except Exception:
			frappe.log_error(
				title="Mobile App Settings dashboards_json",
				message=frappe.get_traceback(),
			)

	return config


def clear_mobile_config_cache():
	frappe.cache().delete_value("erp_analysis_mobile_config")


def get_mobile_config_cached() -> dict[str, Any]:
	cached = frappe.cache().get_value("erp_analysis_mobile_config")
	if cached:
		return cached

	config = build_mobile_config()
	frappe.cache().set_value("erp_analysis_mobile_config", config)
	return config
