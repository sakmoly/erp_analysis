"""Deploy Receivables Phase 2 widgets (trend, collection, DSO, attention)."""

from __future__ import annotations

from typing import Any

import frappe

from erp_analysis.fixtures.operations_dashboard_widgets import RECEIVABLES_PHASE2_WIDGETS
from erp_analysis.fixtures.printechs_b2b_profile import PROFILE_NAME
from erp_analysis.patches.ensure_receivables_dashboard_phase1 import _upsert_widget


def execute() -> dict[str, Any]:
	if not frappe.db.exists("Mobile App Profile", PROFILE_NAME):
		return {"ok": False, "reason": f"Profile {PROFILE_NAME} not found"}

	doc = frappe.get_doc("Mobile App Profile", PROFILE_NAME)
	updated: list[str] = []
	for row in RECEIVABLES_PHASE2_WIDGETS:
		_upsert_widget(doc, row)
		updated.append(row["widget_key"])

	# Upgrade overdue customers widget to RANKING (Phase 2 layout).
	overdue_row = next(
		(w for w in doc.dashboard_widgets or [] if w.widget_key == "receivables_overdue_customers_table"),
		None,
	)
	if overdue_row:
		overdue_row.widget_type = "RANKING"
		overdue_row.sort_order = 21

	doc.save(ignore_permissions=True)
	frappe.db.commit()

	return {
		"ok": True,
		"profile": PROFILE_NAME,
		"updated_widgets": updated,
	}
