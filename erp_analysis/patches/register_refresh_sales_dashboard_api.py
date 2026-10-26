"""Register mobile API to refresh tabSalesDashBoard (daily window)."""

from __future__ import annotations

import frappe

from erp_analysis.services.sales_dashboard_refresh import REFRESH_API_OBJECT_KEY

LABEL = "Refresh Sales Dashboard (Printechs GP data)"


def execute():
	if not frappe.db.exists("Access Object Registry", {"object_key": REFRESH_API_OBJECT_KEY}):
		frappe.get_doc(
			{
				"doctype": "Access Object Registry",
				"object_type": "API",
				"object_key": REFRESH_API_OBJECT_KEY,
				"label": LABEL,
				"is_active": 1,
			}
		).insert(ignore_permissions=True)

	registry_name = frappe.db.get_value(
		"Access Object Registry", {"object_key": REFRESH_API_OBJECT_KEY}, "name"
	)
	if not registry_name:
		frappe.db.commit()
		return {"ok": False}

	updated_profiles: list[str] = []
	for profile_name in frappe.get_all(
		"Access Profile",
		filters={"enabled": 1, "allow_view_all_sales": 1},
		pluck="name",
	):
		doc = frappe.get_doc("Access Profile", profile_name)
		if any(
			(row.access_object == registry_name and row.can_approve)
			for row in doc.access_rules or []
		):
			continue
		existing = next(
			(row for row in doc.access_rules or [] if row.access_object == registry_name),
			None,
		)
		if existing:
			existing.can_view = 1
			existing.can_approve = 1
		else:
			doc.append(
				"access_rules",
				{
					"access_object": registry_name,
					"can_view": 1,
					"can_approve": 1,
				},
			)
		doc.save(ignore_permissions=True)
		updated_profiles.append(profile_name)

	frappe.db.commit()
	return {"ok": True, "object_key": REFRESH_API_OBJECT_KEY, "profiles_updated": updated_profiles}
