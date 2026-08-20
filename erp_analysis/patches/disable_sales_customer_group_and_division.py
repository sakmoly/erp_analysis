"""Disable Customer Group and Channel sales widgets (Division stays enabled)."""

from __future__ import annotations

import frappe

PROFILE = "PRINTECHS-B2B"

DISABLED_WIDGET_KEYS = frozenset(
	{
		"sales_by_customer_group",
		"sales_donut_customer_group",
		"sales_by_channel",
		"sales_donut_channel",
	}
)

ENABLED_DIVISION_WIDGET_KEYS = frozenset(
	{
		"sales_by_division",
		"sales_donut_division",
	}
)


def execute():
	if not frappe.db.exists("Mobile App Profile", PROFILE):
		return {"ok": False, "reason": f"Profile {PROFILE} not found"}

	doc = frappe.get_doc("Mobile App Profile", PROFILE)
	disabled: list[str] = []
	enabled: list[str] = []
	for row in doc.dashboard_widgets or []:
		key = (row.widget_key or "").strip()
		if key in DISABLED_WIDGET_KEYS:
			row.enabled = 0
			disabled.append(key)
		elif key in ENABLED_DIVISION_WIDGET_KEYS:
			row.enabled = 1
			enabled.append(key)

	doc.save(ignore_permissions=True)
	frappe.db.commit()

	from erp_analysis.services.mobile_widgets import clear_dashboard_board_cache

	clear_dashboard_board_cache()
	return {"ok": True, "profile": PROFILE, "disabled_widgets": disabled, "enabled_widgets": enabled}
