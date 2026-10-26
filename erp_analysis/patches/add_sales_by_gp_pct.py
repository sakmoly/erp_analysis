"""Expose GP% on Sales By territory / division / salesperson ranking widgets."""

from __future__ import annotations

import json

import frappe

PROFILE = "PRINTECHS-B2B"

SALES_BY_GP_COLUMNS = """[
  {"key": "dimension", "label": "Name", "flex": 1.4, "align": "left", "min_width": 80},
  {"key": "metric", "label": "Net Sales", "format": "currency_compact", "flex": 1, "align": "right", "min_width": 72},
  {"key": "gp_pct", "label": "GP%", "format": "percent", "width": 52, "align": "right"},
  {"key": "metric_ly", "label": "Net Sales LY", "format": "currency_compact", "flex": 1.2, "align": "right", "min_width": 80},
  {"key": "change_pct", "label": "Δ%", "format": "percent", "width": 48, "align": "right"}
]"""

WIDGET_KEYS = frozenset(
	{
		"sales_by_territory",
		"sales_by_division",
		"sales_by_salesperson",
	}
)


def execute():
	if not frappe.db.exists("Mobile App Profile", PROFILE):
		return {"ok": False, "reason": f"Profile {PROFILE} not found"}

	doc = frappe.get_doc("Mobile App Profile", PROFILE)
	updated: list[str] = []
	for row in doc.dashboard_widgets or []:
		key = (row.widget_key or "").strip()
		if key not in WIDGET_KEYS:
			continue
		row.table_columns_json = SALES_BY_GP_COLUMNS
		updated.append(key)

	if not updated:
		return {"ok": True, "profile": PROFILE, "updated": [], "note": "No matching widgets on profile"}

	doc.save(ignore_permissions=True)
	frappe.db.commit()

	from erp_analysis.services.mobile_widgets import clear_dashboard_board_cache

	clear_dashboard_board_cache()
	return {"ok": True, "profile": PROFILE, "updated": updated}
