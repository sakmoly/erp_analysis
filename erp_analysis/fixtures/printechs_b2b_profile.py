"""PRINTECHS-B2B Mobile App Profile fixture (Phase J — opt-in template only)."""

from __future__ import annotations

from typing import Any, Optional

import frappe

from erp_analysis.mobile_config import default_modules
from erp_analysis.mobile_module_icons import DEFAULT_MODULE_ICON_KEYS
from erp_analysis.services.analytics_dimensions import _dashboard_join_path, _legacy_dimension_specs
from erp_analysis.services.mobile_dimensions import validate_dimension_definition
from erp_analysis.utils.schema import has_field

PROFILE_NAME = "PRINTECHS-B2B"


def _module_rows() -> list[dict[str, Any]]:
	labels = {
		"sales": "Sales",
		"receivables": "Receivables",
		"inventory": "Inventory",
		"approvals": "Approvals",
		"catalogue": "Catalogue",
		"push": "Notifications",
		"settings": "Settings",
		"executive": "Executive",
		"collection": "Collection",
		"sales_performance": "Sales Performance",
		"sales_orders": "Sales Orders",
		"payables": "Payables",
		"purchase": "Purchase",
		"customer_360": "Customer 360",
		"profitability": "Profitability",
		"exceptions": "Exceptions",
		"approval_analytics": "Approval Analytics",
	}
	rows = []
	for idx, (key, enabled) in enumerate(default_modules().items()):
		if not enabled:
			continue
		rows.append(
			{
				"module_key": key,
				"label": labels.get(key, key.replace("_", " ").title()),
				"enabled": 1,
				"sort_order": idx,
				"route_key": key,
				"icon_key": DEFAULT_MODULE_ICON_KEYS.get(key),
			}
		)
	return rows


def _dimension_rows() -> list[dict[str, Any]]:
	"""Only dimensions with valid fields on this site."""
	specs = {**_legacy_dimension_specs(), **_legacy_dashboard_specs()}
	extra = {
		"customer": ("Customer", "Customer", "territory"),
		"item_group": ("Item Group", "Item Group", "name"),
	}
	for key, (label, doctype, field) in extra.items():
		if has_field(doctype, field):
			specs[key] = {
				"dimension_key": key,
				"label": label,
				"enabled": 1,
				"source_doctype": doctype,
				"source_field": field,
				"source_mode": "FIELD",
				"allow_filter": 1,
				"allow_group_by": 1,
				"allow_sort": 0,
			}

	rows: list[dict[str, Any]] = []
	for idx, (key, spec) in enumerate(sorted(specs.items())):
		if spec.get("source_mode", "FIELD") == "FIELD" and not spec.get("source_field"):
			continue
		row = {
			"dimension_key": key,
			"label": spec.get("label") or key.replace("_", " ").title(),
			"enabled": 1,
			"source_doctype": spec.get("source_doctype"),
			"source_field": spec.get("source_field"),
			"source_mode": spec.get("source_mode") or "FIELD",
			"join_path_json": spec.get("join_path_json"),
			"allow_filter": 1,
			"allow_group_by": 1,
			"allow_sort": 0,
			"sort_order": idx,
		}
		try:
			validate_dimension_definition(type("Row", (), row)())
			rows.append(row)
		except Exception:
			continue
	return rows


def _legacy_dashboard_specs() -> dict[str, dict[str, Any]]:
	if not frappe.db.table_exists("SalesDashBoard"):
		return {}
	return {
		"salesperson": {
			"dimension_key": "salesperson",
			"label": "Salesperson",
			"enabled": 1,
			"source_mode": "DERIVED",
			"join_path_json": _dashboard_join_path("SalesDashBoard", "Sales_Person"),
		},
		"division": {
			"dimension_key": "division",
			"label": "Division",
			"enabled": 1,
			"source_mode": "DERIVED",
			"join_path_json": _dashboard_join_path("SalesDashBoard", "Division"),
		},
	}


def build_profile_doc_dict(company: Optional[str] = None) -> dict[str, Any]:
	return {
		"doctype": "Mobile App Profile",
		"profile_name": PROFILE_NAME,
		"business_type": "B2B",
		"enabled": 1,
		"company": company,
		"default_dashboard": "home",
		"app_title": "Business Insight",
		"app_subtitle": "Printechs B2B",
		"primary_locale": "en",
		"currency_source": "Company Default",
		"modules": _module_rows(),
		"dimensions": _dimension_rows(),
		"dashboards": [
			{
				"dashboard_key": "home",
				"label": "Sales Home",
				"enabled": 1,
				"sort_order": 0,
				"icon_key": "home-outline",
			},
			{
				"dashboard_key": "receivables_overview",
				"label": "Receivables",
				"enabled": 1,
				"sort_order": 1,
				"icon_key": "wallet-outline",
			},
		],
		"dashboard_widgets": [
			{
				"widget_key": "sales_card",
				"label": "Sales Performance",
				"widget_type": "PIE",
				"dashboard_id": "home",
				"module_key": "sales",
				"metric_key": "net_sales",
				"dimension_key": "territory",
				"config_json": '{"compare": "ly", "drill_path": ["territory", "brand"]}',
				"enabled": 1,
				"sort_order": 0,
			},
			{
				"widget_key": "goto_receivables",
				"label": "Receivables Dashboard",
				"widget_type": "LINK",
				"dashboard_id": "home",
				"module_key": "receivables",
				"config_json": '{"action": {"type": "navigate", "target": "dashboard", "dashboard_id": "receivables_overview"}}',
				"enabled": 1,
				"sort_order": 1,
			},
			{
				"widget_key": "receivables_card",
				"label": "Receivables",
				"widget_type": "LIST",
				"dashboard_id": "receivables_overview",
				"module_key": "receivables",
				"enabled": 1,
				"sort_order": 0,
			},
			{
				"widget_key": "inventory_card",
				"label": "Inventory",
				"widget_type": "LIST",
				"dashboard_id": "home",
				"module_key": "inventory",
				"enabled": 1,
				"sort_order": 2,
			},
		],
	}


def ensure_profile(company: Optional[str] = None, *, update_existing: bool = False) -> dict[str, Any]:
	"""
	Create PRINTECHS-B2B if missing.

	Does NOT link Access Profiles, Users, or Mobile App Settings default.
	"""
	if not frappe.db.exists("DocType", "Mobile App Profile"):
		return {"ok": False, "reason": "Mobile App Profile DocType missing — run bench migrate first"}

	if frappe.db.exists("Mobile App Profile", PROFILE_NAME):
		if not update_existing:
			return {"ok": True, "created": False, "name": PROFILE_NAME, "message": "Profile already exists"}
		doc = frappe.get_doc("Mobile App Profile", PROFILE_NAME)
		payload = build_profile_doc_dict(company=company)
		for key, value in payload.items():
			if key in ("doctype", "profile_name"):
				continue
			doc.set(key, value)
		doc.save(ignore_permissions=True)
		frappe.db.commit()
		return {"ok": True, "created": False, "updated": True, "name": PROFILE_NAME}

	doc = frappe.get_doc(build_profile_doc_dict(company=company))
	doc.insert(ignore_permissions=True)
	frappe.db.commit()
	return {
		"ok": True,
		"created": True,
		"name": PROFILE_NAME,
		"modules": len(doc.modules or []),
		"dimensions": len(doc.dimensions or []),
	}
