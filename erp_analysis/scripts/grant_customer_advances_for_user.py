"""Ensure Customer Advances API access for one user (Access Profile lines)."""

from __future__ import annotations

import frappe

from erp_analysis.fixtures.printechs_b2b_profile import PROFILE_NAME
from erp_analysis.mobile_config import clear_mobile_config_cache
from erp_analysis.patches.sync_mobile_access_registry import ensure_registry_rows, sync_access_profiles
from erp_analysis.permissions.access_profile import clear_caches

def _enable_collection_module_on_mobile_profile(profile_name: str = PROFILE_NAME) -> bool:
	if not frappe.db.exists("Mobile App Profile", profile_name):
		return False
	doc = frappe.get_doc("Mobile App Profile", profile_name)
	existing = next(
		(m for m in doc.modules or [] if (m.module_key or "").strip().lower() == "collection"),
		None,
	)
	if existing:
		if not existing.enabled:
			existing.enabled = 1
			doc.save(ignore_permissions=True)
			return True
		return False
	doc.append(
		"modules",
		{
			"module_key": "collection",
			"label": "Collection",
			"enabled": 1,
			"sort_order": 870,
			"route_key": "collection",
			"screen_type": "module",
		},
	)
	doc.save(ignore_permissions=True)
	return True


OBJECT_KEYS = (
	"erp_analysis.collection.get_customer_advances",
	"erp_analysis.collection.get_customer_advances_customers_chart",
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

	module_changed = _enable_collection_module_on_mobile_profile()

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
		"mobile_profile_collection_module": module_changed,
		"object_access": results,
	}
