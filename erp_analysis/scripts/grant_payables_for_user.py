"""Ensure payables menu + API access on a user's Access Profile."""

from __future__ import annotations

import frappe

from erp_analysis.permissions.access_profile import clear_caches

PAYABLES_OBJECT_KEYS = (
	"menu_payables",
	"erp_analysis.payables.get_payables_dashboard",
	"erp_analysis.payables.get_payment_planning",
	"menu_purchase_performance",
	"erp_analysis.purchase.get_purchase_dashboard",
	"erp_analysis.purchase.get_open_purchase_orders",
)


def grant(user: str = "sakeer@printechs.com", company: str | None = None) -> dict:
	filters: dict = {"user": user, "enabled": 1}
	if company:
		filters["company"] = company
	profile_name = frappe.db.get_value("Access Profile", filters, "name")
	if not profile_name:
		profile_name = frappe.db.get_value("Access Profile", {"user": user, "enabled": 1}, "name")
	if not profile_name:
		frappe.throw(f"No enabled Access Profile for user {user}")

	profile = frappe.get_doc("Access Profile", profile_name)
	changed = False
	for object_key in PAYABLES_OBJECT_KEYS:
		registry_name = frappe.db.get_value(
			"Access Object Registry", {"object_key": object_key}, "name"
		)
		if not registry_name:
			continue
		existing = next(
			(row for row in profile.access_rules or [] if row.access_object == registry_name),
			None,
		)
		if existing:
			if not existing.can_view:
				existing.can_view = 1
				changed = True
			if not existing.active:
				existing.active = 1
				changed = True
		else:
			profile.append(
				"access_rules",
				{
					"access_object": registry_name,
					"can_view": 1,
					"can_approve": 0,
					"active": 1,
				},
			)
			changed = True

	if changed:
		profile.save(ignore_permissions=True)
	frappe.db.commit()
	clear_caches(user=user)
	return {
		"ok": True,
		"user": user,
		"access_profile": profile_name,
		"changed": changed,
		"object_keys": PAYABLES_OBJECT_KEYS,
	}
