"""Sales By drill: show full tabSalesDashBoard Sub_Group names (no prefix strip)."""

from __future__ import annotations

import json

import frappe

from erp_analysis.patches.fix_division_widget_drill import DIVISION_DRILL_CONFIG, DIVISION_WIDGET_KEYS

PROFILE = "PRINTECHS-B2B"


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
	for row in doc.dashboard_widgets or []:
		key = (row.widget_key or "").strip()
		if key in DIVISION_WIDGET_KEYS:
			row.config_json = _merge_config(row.config_json, DIVISION_DRILL_CONFIG)

	for dim in doc.dimensions or []:
		key = (dim.dimension_key or "").strip().lower()
		if key != "sub_group":
			continue
		dim.label = "Item Group (Sub_Group)"
		raw = dim.join_path_json
		try:
			join_path = json.loads(raw) if raw else {}
		except Exception:
			join_path = {}
		if isinstance(join_path, dict):
			join_path.pop("label_transform", None)
			dim.join_path_json = json.dumps(join_path, separators=(",", ":"))

	doc.save(ignore_permissions=True)
	frappe.db.commit()

	from erp_analysis.services.mobile_widgets import clear_dashboard_board_cache

	clear_dashboard_board_cache()
	return {"ok": True, "profile": PROFILE}
