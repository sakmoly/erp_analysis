"""Enable receivables_card territory widget on receivables_overview (PRINTECHS-B2B)."""

from __future__ import annotations

import json

import frappe

PROFILE_NAME = "PRINTECHS-B2B"
WIDGET_KEY = "receivables_card"
CONFIG = {
	"payload_source": "legacy_chart",
	"legacy_method": "erp_analysis.receivables.get_receivables_dashboard",
	"rows_key": "territory_totals",
	"label_field": "territory",
	"value_field": "outstanding",
	"section_title": "Receivables Card",
	"row_group": "receivables_card",
}


def execute():
	if not frappe.db.exists("Mobile App Profile", PROFILE_NAME):
		return {"ok": False, "reason": f"Profile {PROFILE_NAME} not found"}

	doc = frappe.get_doc("Mobile App Profile", PROFILE_NAME)
	existing = None
	for row in doc.dashboard_widgets or []:
		if (row.widget_key or "").strip() == WIDGET_KEY:
			existing = row
			break

	config_json = json.dumps(CONFIG, separators=(",", ":"))
	if existing:
		existing.label = "Receivables Card"
		existing.widget_type = "PIE"
		existing.dashboard_id = "receivables_overview"
		existing.module_key = "receivables"
		existing.metric_key = "outstanding"
		existing.dimension_key = "territory"
		existing.enabled = 1
		existing.sort_order = 5
		existing.config_json = config_json
	else:
		doc.append(
			"dashboard_widgets",
			{
				"widget_key": WIDGET_KEY,
				"label": "Receivables Card",
				"widget_type": "PIE",
				"dashboard_id": "receivables_overview",
				"module_key": "receivables",
				"metric_key": "outstanding",
				"dimension_key": "territory",
				"enabled": 1,
				"sort_order": 5,
				"config_json": config_json,
			},
		)

	doc.save(ignore_permissions=True)
	frappe.db.commit()

	from erp_analysis.services.mobile_widgets import clear_dashboard_board_cache

	clear_dashboard_board_cache()
	return {"ok": True, "profile": PROFILE_NAME, "widget_key": WIDGET_KEY}
