"""Sales overview total KPI: SalesDashBoard Net_Amount (same scope as division widgets)."""

from __future__ import annotations

import json

import frappe

PROFILE = "PRINTECHS-B2B"

KPI_WIDGET_KEYS = frozenset({"sales_total_kpi", "sales_dash_net_ytd_kpi"})

DASHBOARD_KPI_CONFIG = {"data_source": "dashboard"}


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

	if not frappe.db.table_exists("SalesDashBoard"):
		return {"ok": False, "reason": "SalesDashBoard table missing"}

	doc = frappe.get_doc("Mobile App Profile", PROFILE)
	updated = []
	for row in doc.dashboard_widgets or []:
		key = (row.widget_key or "").strip()
		if key not in KPI_WIDGET_KEYS:
			continue
		row.config_json = _merge_config(row.config_json, DASHBOARD_KPI_CONFIG)
		updated.append(key)

	if updated:
		doc.save(ignore_permissions=True)
		frappe.db.commit()

	return {"ok": True, "updated": updated}
