"""Ensure Management Attention cards use compact (Million) formatting."""

from __future__ import annotations

import json

import frappe

PROFILE = "PRINTECHS-B2B"
WIDGET_KEY = "sales_management_attention"
CONFIG = {
	"data_source": "attention",
	"section": "all",
	"section_title": "Management Attention",
	"format": "currency_compact",
	"row_limit": 4,
	"decline_threshold_pct": 10,
}


def execute():
	if not frappe.db.exists("Mobile App Profile", PROFILE):
		return {"ok": False, "reason": f"Profile {PROFILE} not found"}

	doc = frappe.get_doc("Mobile App Profile", PROFILE)
	target = None
	for row in doc.dashboard_widgets or []:
		if (row.widget_key or "").strip() == WIDGET_KEY:
			target = row
			break

	config_json = json.dumps(CONFIG, separators=(",", ":"))
	if target:
		target.config_json = config_json
		target.period = target.period or "ytd"
		target.enabled = 1
	else:
		doc.append(
			"dashboard_widgets",
			{
				"widget_key": WIDGET_KEY,
				"label": "Management Attention",
				"widget_type": "LIST",
				"dashboard_id": "sales_overview",
				"module_key": "sales",
				"period": "ytd",
				"enabled": 1,
				"sort_order": 90,
				"config_json": config_json,
			},
		)

	doc.save(ignore_permissions=True)
	frappe.db.commit()

	from erp_analysis.services.mobile_widgets import clear_dashboard_board_cache

	clear_dashboard_board_cache()
	return {"ok": True, "profile": PROFILE, "widget_key": WIDGET_KEY}
