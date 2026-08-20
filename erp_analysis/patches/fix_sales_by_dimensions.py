"""Register Sales By dimensions and rename Channel widgets to Division."""

from __future__ import annotations

import json

import frappe

from erp_analysis.services.analytics_dimensions import _dashboard_join_path

PROFILE = "PRINTECHS-B2B"

DIMENSIONS = [
	{
		"dimension_key": "customer_group",
		"label": "Customer Group",
		"enabled": 1,
		"source_doctype": "Sales Invoice",
		"source_field": "customer_group",
		"source_mode": "FIELD",
		"allow_filter": 1,
		"allow_group_by": 1,
		"allow_sort": 0,
		"sort_order": 10,
	},
	{
		"dimension_key": "salesperson",
		"label": "Salesperson",
		"enabled": 1,
		"source_mode": "DERIVED",
		"join_path_json": _dashboard_join_path("SalesDashBoard", "Sales_Person"),
		"allow_filter": 1,
		"allow_group_by": 1,
		"allow_sort": 0,
		"sort_order": 11,
	},
	{
		"dimension_key": "division",
		"label": "Division",
		"enabled": 1,
		"source_mode": "DERIVED",
		"join_path_json": _dashboard_join_path("SalesDashBoard", "Division"),
		"allow_filter": 1,
		"allow_group_by": 1,
		"allow_sort": 0,
		"sort_order": 12,
	},
]

SALES_BY_CONFIG = {
	"compare": "ly",
	"section_title": "Sales By",
	"row_limit": 5,
}

SALESPERSON_CONFIG = {
	**SALES_BY_CONFIG,
	"row_limit": 10,
}

DISABLED_SALES_BY_WIDGETS = frozenset(
	{
		"sales_by_customer_group",
		"sales_donut_customer_group",
		"sales_by_channel",
		"sales_donut_channel",
	}
)

WIDGET_RENAMES = {
	"sales_by_channel": {
		"widget_key": "sales_by_division",
		"label": "Sales By Division",
		"dimension_key": "division",
	},
	"sales_donut_channel": {
		"widget_key": "sales_donut_division",
		"label": "Division",
		"dimension_key": "division",
	},
}


def _ensure_dimension(doc, spec: dict) -> None:
	key = (spec.get("dimension_key") or "").strip().lower()
	for row in doc.dimensions or []:
		if (row.dimension_key or "").strip().lower() == key:
			for field, value in spec.items():
				setattr(row, field, value)
			return
	doc.append("dimensions", spec)


def _merge_config(existing: str | None, updates: dict) -> str:
	config = {}
	if existing:
		try:
			parsed = json.loads(existing)
			if isinstance(parsed, dict):
				config = parsed
		except Exception:
			pass
	config.update(updates)
	return json.dumps(config, separators=(",", ":"))


def execute():
	if not frappe.db.exists("Mobile App Profile", PROFILE):
		return {"ok": False, "reason": f"Profile {PROFILE} not found"}

	doc = frappe.get_doc("Mobile App Profile", PROFILE)

	for spec in DIMENSIONS:
		_ensure_dimension(doc, spec)

	for row in doc.dashboard_widgets or []:
		key = (row.widget_key or "").strip()
		if key in DISABLED_SALES_BY_WIDGETS:
			row.enabled = 0
			continue
		if key == "sales_by_salesperson":
			row.config_json = _merge_config(row.config_json, SALESPERSON_CONFIG)
			if not row.period:
				row.period = "ytd"
		elif key in ("sales_by_customer_group", "sales_by_territory", "sales_by_division", "sales_by_channel"):
			row.config_json = _merge_config(row.config_json, SALES_BY_CONFIG)
			if not row.period:
				row.period = "ytd"

		rename = WIDGET_RENAMES.get(key)
		if rename:
			for field, value in rename.items():
				setattr(row, field, value)
			row.config_json = _merge_config(row.config_json, SALES_BY_CONFIG)

	# Ensure renamed keys exist even if old keys were already migrated.
	for row in doc.dashboard_widgets or []:
		if (row.widget_key or "").strip() in DISABLED_SALES_BY_WIDGETS:
			row.enabled = 0
			continue
		if (row.widget_key or "").strip() == "sales_by_division":
			row.dimension_key = "division"
			row.label = "Sales By Division"
			row.config_json = _merge_config(row.config_json, SALES_BY_CONFIG)
		if (row.widget_key or "").strip() == "sales_donut_division":
			row.dimension_key = "division"
			row.label = "Division"

	doc.save(ignore_permissions=True)
	frappe.db.commit()

	from erp_analysis.services.mobile_widgets import clear_dashboard_board_cache

	clear_dashboard_board_cache()
	return {
		"ok": True,
		"profile": PROFILE,
		"dimensions_added": [d["dimension_key"] for d in DIMENSIONS],
		"widgets_renamed": list(WIDGET_RENAMES.keys()),
	}
