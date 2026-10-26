"""Division tab drill: profile dimensions + drill_path (division → sub_group → brand)."""

from __future__ import annotations

import json

import frappe

from erp_analysis.services.analytics_dimensions import _dashboard_join_path

PROFILE = "PRINTECHS-B2B"

EXTRA_DIMENSIONS = [
	{
		"dimension_key": "sub_group",
		"label": "Item Group",
		"enabled": 1,
		"source_mode": "DERIVED",
		"join_path_json": _dashboard_join_path("SalesDashBoard", "Sub_Group"),
		"allow_filter": 1,
		"allow_group_by": 1,
		"allow_sort": 0,
		"sort_order": 13,
	},
	{
		"dimension_key": "brand",
		"label": "Brand",
		"enabled": 1,
		"source_mode": "DERIVED",
		"join_path_json": _dashboard_join_path("SalesDashBoard", "Brand"),
		"allow_filter": 1,
		"allow_group_by": 1,
		"allow_sort": 0,
		"sort_order": 14,
	},
]

DIVISION_DRILL_CONFIG = {
	"compare": "ly",
	"section_title": "Sales By",
	"row_limit": 5,
	"drill_path": ["division", "sub_group", "brand"],
	"drill_views": {"0": "donut", "1": "table", "2": "table"},
	"sub_group_label_display": "full",
	"strip_division_prefix_from_sub_group": False,
	"drill_row_label_field": "dimension_value",
}

DIVISION_WIDGET_KEYS = frozenset({"sales_by_division", "sales_donut_division"})


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
	for spec in EXTRA_DIMENSIONS:
		_ensure_dimension(doc, spec)

	for row in doc.dashboard_widgets or []:
		key = (row.widget_key or "").strip()
		if key in DIVISION_WIDGET_KEYS:
			row.config_json = _merge_config(row.config_json, DIVISION_DRILL_CONFIG)
			if not row.period:
				row.period = "ytd"

	doc.save(ignore_permissions=True)
	frappe.db.commit()

	from erp_analysis.services.mobile_widgets import clear_dashboard_board_cache

	clear_dashboard_board_cache()
	return {"ok": True, "profile": PROFILE, "widgets": list(DIVISION_WIDGET_KEYS)}
