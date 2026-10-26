"""Add Open Sales Orders KPI + drill list on sales_overview (PRINTECHS-B2B)."""

from __future__ import annotations

from typing import Any

import frappe

from erp_analysis.fixtures.printechs_b2b_profile import PROFILE_NAME
from erp_analysis.fixtures.sales_dashboard_widgets import SALES_DASHBOARD_WIDGETS
from erp_analysis.patches.ensure_receivables_dashboard_phase1 import _upsert_widget

_OPEN_SO_WIDGET_KEYS = frozenset({"sales_orders_kpi", "sales_open_orders_list"})


def execute() -> dict[str, Any]:
	from erp_analysis.patches.sync_mobile_access_registry import ensure_registry_rows, sync_access_profiles
	from erp_analysis.services.mobile_widgets import clear_dashboard_board_cache

	if not frappe.db.exists("Mobile App Profile", PROFILE_NAME):
		return {"ok": False, "reason": f"Profile {PROFILE_NAME} not found"}

	key_to_name = ensure_registry_rows()
	sync_access_profiles(key_to_name)

	doc = frappe.get_doc("Mobile App Profile", PROFILE_NAME)
	updated: list[str] = []
	for row in SALES_DASHBOARD_WIDGETS:
		if row["widget_key"] not in _OPEN_SO_WIDGET_KEYS:
			continue
		_upsert_widget(doc, row)
		updated.append(row["widget_key"])

	doc.save(ignore_permissions=True)
	frappe.db.commit()
	clear_dashboard_board_cache()
	return {"ok": True, "profile": PROFILE_NAME, "updated_widgets": updated}
