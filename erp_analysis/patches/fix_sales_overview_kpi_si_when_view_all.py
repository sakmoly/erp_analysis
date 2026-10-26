"""Remove forced dashboard KPI source; company-wide view uses Sales Invoice totals."""

from __future__ import annotations

import json

import frappe

PROFILE = "PRINTECHS-B2B"
KPI_WIDGET_KEYS = frozenset({"sales_total_kpi", "sales_dash_net_ytd_kpi"})


def execute():
	if not frappe.db.exists("Mobile App Profile", PROFILE):
		return {"ok": False}

	doc = frappe.get_doc("Mobile App Profile", PROFILE)
	updated = []
	for row in doc.dashboard_widgets or []:
		key = (row.widget_key or "").strip()
		if key not in KPI_WIDGET_KEYS or not row.config_json:
			continue
		try:
			config = json.loads(row.config_json)
		except Exception:
			continue
		if not isinstance(config, dict) or "data_source" not in config:
			continue
		config.pop("data_source", None)
		row.config_json = json.dumps(config, separators=(",", ":"))
		updated.append(key)

	if updated:
		doc.save(ignore_permissions=True)
		frappe.db.commit()
	return {"ok": True, "updated": updated}
