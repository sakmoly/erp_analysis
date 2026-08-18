"""Wire bottom-nav Receivables tab to receivables_overview dashboard."""

from __future__ import annotations

from typing import Any

import frappe

from erp_analysis.fixtures.printechs_b2b_profile import PROFILE_NAME
from erp_analysis.fixtures.shell_module_dashboards import SHELL_MODULE_TO_DASHBOARD


def execute() -> dict[str, Any]:
	if not frappe.db.exists("Mobile App Profile", PROFILE_NAME):
		return {"ok": False, "reason": f"Profile {PROFILE_NAME} not found"}

	doc = frappe.get_doc("Mobile App Profile", PROFILE_NAME)
	updated: list[str] = []

	for module_key, dashboard_id in SHELL_MODULE_TO_DASHBOARD.items():
		row = next((m for m in doc.modules or [] if m.module_key == module_key), None)
		if not row:
			continue
		row.screen_type = "dashboard"
		row.dashboard_id = dashboard_id
		row.route_key = row.route_key or module_key
		updated.append(f"{module_key}->{dashboard_id}")

	doc.save(ignore_permissions=True)
	frappe.db.commit()

	return {"ok": True, "profile": PROFILE_NAME, "wired_modules": updated}
