"""Replace sales_overview Total Orders KPI with COGS on PRINTECHS-B2B profile."""

from __future__ import annotations

import json

import frappe

PROFILE = "PRINTECHS-B2B"
OLD_KEY = "sales_orders_kpi"
NEW_KEY = "sales_cogs_kpi"
CONFIG = {
	"compare": "ly",
	"format": "currency_compact",
	"section_title": "Overview KPIs",
	"kpi_id": "sales_cogs_kpi",
	"row_group": "sales_overview_kpis",
	"layout": "row",
	"columns": 2,
}


def execute():
	if not frappe.db.exists("Mobile App Profile", PROFILE):
		return {"ok": False, "reason": f"Profile {PROFILE} not found"}

	doc = frappe.get_doc("Mobile App Profile", PROFILE)
	target = None
	for row in doc.dashboard_widgets or []:
		key = (row.widget_key or "").strip()
		if key in (OLD_KEY, NEW_KEY):
			target = row
			break

	config_json = json.dumps(CONFIG, separators=(",", ":"))
	if target:
		target.widget_key = NEW_KEY
		target.label = "COGS (Cost of Goods Sold)"
		target.widget_type = "KPI"
		target.dashboard_id = "sales_overview"
		target.module_key = "sales"
		target.metric_key = "cogs"
		target.period = "ytd"
		target.show_ly = 1
		target.show_currency_symbol = 1
		target.enabled = 1
		target.config_json = config_json
	else:
		doc.append(
			"dashboard_widgets",
			{
				"widget_key": NEW_KEY,
				"label": "COGS (Cost of Goods Sold)",
				"widget_type": "KPI",
				"dashboard_id": "sales_overview",
				"module_key": "sales",
				"metric_key": "cogs",
				"period": "ytd",
				"show_ly": 1,
				"show_currency_symbol": 1,
				"enabled": 1,
				"sort_order": 11,
				"config_json": config_json,
			},
		)

	doc.save(ignore_permissions=True)
	frappe.db.commit()

	from erp_analysis.services.mobile_widgets import clear_dashboard_board_cache

	clear_dashboard_board_cache()
	return {"ok": True, "profile": PROFILE, "widget_key": NEW_KEY, "replaced": OLD_KEY}
