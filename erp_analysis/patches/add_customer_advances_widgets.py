"""Add customer advances KPI + ranking on receivables_overview (PRINTECHS-B2B)."""

from __future__ import annotations

from typing import Any

import frappe

from erp_analysis.fixtures.operations_dashboard_widgets import RECEIVABLES_PHASE1_WIDGETS
from erp_analysis.fixtures.printechs_b2b_profile import PROFILE_NAME
from erp_analysis.patches.ensure_receivables_dashboard_phase1 import _upsert_widget

_ADVANCES_WIDGET_KEYS = frozenset(
	{"receivables_customer_advances_kpi", "receivables_customer_advances_ranking"}
)


def execute() -> dict[str, Any]:
	from erp_analysis.patches.sync_mobile_access_registry import ensure_registry_rows, sync_access_profiles

	if not frappe.db.exists("Mobile App Profile", PROFILE_NAME):
		return {"ok": False, "reason": f"Profile {PROFILE_NAME} not found"}

	key_to_name = ensure_registry_rows()
	sync_access_profiles(key_to_name)

	doc = frappe.get_doc("Mobile App Profile", PROFILE_NAME)
	updated: list[str] = []
	for row in RECEIVABLES_PHASE1_WIDGETS:
		if row["widget_key"] not in _ADVANCES_WIDGET_KEYS:
			continue
		_upsert_widget(doc, row)
		updated.append(row["widget_key"])

	doc.save(ignore_permissions=True)
	frappe.db.commit()

	return {"ok": True, "profile": PROFILE_NAME, "updated_widgets": updated}
