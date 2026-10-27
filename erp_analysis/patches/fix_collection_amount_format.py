"""Use full SAR integers (no K/M) for collection KPI widgets."""

from __future__ import annotations

import json

import frappe

WIDGET_KEYS = (
	"receivables_collected_mtd_kpi",
	"receivables_collected_ytd_kpi",
	"collection_mtd",
	"collection_ytd",
)


def _set_format_currency_integer(config_json: str | None) -> str:
	config = json.loads(config_json or "{}")
	if not isinstance(config, dict):
		config = {}
	config["format"] = "currency_integer"
	return json.dumps(config, separators=(",", ":"))


def execute():
	updated: list[str] = []
	if frappe.db.table_exists("Mobile Dashboard Widget"):
		for key in WIDGET_KEYS:
			for name in frappe.get_all("Mobile Dashboard Widget", filters={"widget_key": key}, pluck="name"):
				doc = frappe.get_doc("Mobile Dashboard Widget", name)
				doc.config_json = _set_format_currency_integer(doc.config_json)
				doc.save(ignore_permissions=True)
				updated.append(key)

	if frappe.db.table_exists("Mobile App Profile"):
		for profile in frappe.get_all("Mobile App Profile", pluck="name"):
			doc = frappe.get_doc("Mobile App Profile", profile)
			changed = False
			for row in doc.dashboard_widgets or []:
				key = (row.widget_key or "").strip()
				if key not in WIDGET_KEYS:
					continue
				row.config_json = _set_format_currency_integer(row.config_json)
				changed = True
				updated.append(f"{profile}:{key}")
			if changed:
				doc.save(ignore_permissions=True)

	frappe.db.commit()

	try:
		from erp_analysis.services.mobile_widgets import clear_dashboard_board_cache

		clear_dashboard_board_cache()
	except Exception:
		pass

	return {"updated": sorted(set(updated))}
