"""Ensure Open Sales Orders dashboard drill API access for one user."""

from __future__ import annotations

import frappe

from erp_analysis.mobile_config import clear_mobile_config_cache
from erp_analysis.patches.sync_mobile_access_registry import ensure_registry_rows, sync_access_profiles
from erp_analysis.permissions.access_profile import clear_caches

OBJECT_KEYS = (
	"erp_analysis.sales_orders.get_open_sales_orders",
	"erp_analysis.sales_orders.get_open_sales_order_items",
)


def run(user: str = "sakeer@printechs.com", company: str | None = None) -> dict:
	if not frappe.db.exists("DocType", "Access Object Registry"):
		return {"ok": False, "reason": "Access Object Registry missing"}

	key_to_name = ensure_registry_rows()
	sync_access_profiles(key_to_name)

	filters: dict = {"user": user, "enabled": 1}
	if company:
		filters["company"] = company
	profile_name = frappe.db.get_value("Access Profile", filters, "name")
	if not profile_name:
		profile_name = frappe.db.get_value("Access Profile", {"user": user, "enabled": 1}, "name")
	if not profile_name:
		frappe.throw(f"No enabled Access Profile for user {user}")

	registry_names = [key_to_name[k] for k in OBJECT_KEYS if k in key_to_name]
	profile = frappe.get_doc("Access Profile", profile_name)
	by_object = {row.access_object: row for row in profile.access_rules if row.access_object}
	changed = False
	for registry_name in registry_names:
		line = by_object.get(registry_name)
		if line:
			if not line.can_view or not line.active:
				line.can_view = 1
				line.active = 1
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
	clear_caches()
	clear_mobile_config_cache()

	frappe.set_user(user)
	from erp_analysis.access_context import require_object_access

	results: dict[str, str] = {}
	for ok in OBJECT_KEYS:
		try:
			require_object_access(ok, user=user, company=company or profile.company)
			results[ok] = "allowed"
		except Exception as exc:
			results[ok] = str(exc)

	return {
		"ok": True,
		"user": user,
		"access_profile": profile_name,
		"changed": changed,
		"object_access": results,
	}
