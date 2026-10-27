"""Ensure collection module + API access on a user's Access Profile."""

from __future__ import annotations

import frappe

from erp_analysis.fixtures.printechs_b2b_profile import PROFILE_NAME
from erp_analysis.mobile_config import clear_mobile_config_cache
from erp_analysis.patches.sync_mobile_access_registry import ensure_registry_rows, sync_access_profiles
from erp_analysis.permissions.access_profile import clear_caches

COLLECTION_OBJECT_KEYS = (
	"erp_analysis.collection.get_collection_dashboard",
	"erp_analysis.collection.get_collection_attention",
	"erp_analysis.collection.get_collection_payments",
	"erp_analysis.collection.get_customer_advances",
	"erp_analysis.collection.get_customer_advances_customers_chart",
)


def _enable_collection_module_on_mobile_profile(profile_name: str = PROFILE_NAME) -> bool:
	if not frappe.db.exists("Mobile App Profile", profile_name):
		return False
	doc = frappe.get_doc("Mobile App Profile", profile_name)
	existing = next(
		(m for m in doc.modules or [] if (m.module_key or "").strip().lower() == "collection"),
		None,
	)
	if existing:
		changed = False
		if not existing.enabled:
			existing.enabled = 1
			changed = True
		if not (existing.route_key or "").strip():
			existing.route_key = "collection"
			changed = True
		if changed:
			doc.save(ignore_permissions=True)
		return changed
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


def grant(user: str = "sakeer@printechs.com", company: str | None = None) -> dict:
	if frappe.db.exists("DocType", "Access Object Registry"):
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

	profile = frappe.get_doc("Access Profile", profile_name)
	by_object = {row.access_object: row for row in profile.access_rules if row.access_object}
	changed = False
	for object_key in COLLECTION_OBJECT_KEYS:
		registry_name = frappe.db.get_value(
			"Access Object Registry", {"object_key": object_key}, "name"
		)
		if not registry_name:
			continue
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

	mobile_profile = frappe.db.get_value("Access Profile", profile_name, "mobile_app_profile") or PROFILE_NAME
	module_changed = _enable_collection_module_on_mobile_profile(mobile_profile)

	frappe.db.commit()
	clear_caches(user=user)
	clear_mobile_config_cache()

	granted = []
	for object_key in COLLECTION_OBJECT_KEYS:
		reg = frappe.db.get_value("Access Object Registry", {"object_key": object_key}, "name")
		if not reg:
			granted.append({"object_key": object_key, "can_view": None, "note": "not in registry"})
			continue
		line = frappe.db.get_value(
			"Access Profile Line",
			{"parent": profile_name, "access_object": reg},
			["can_view", "active"],
			as_dict=True,
		)
		granted.append({"object_key": object_key, **(line or {})})

	return {
		"ok": True,
		"user": user,
		"access_profile": profile_name,
		"mobile_app_profile": mobile_profile,
		"access_changed": changed,
		"mobile_module_changed": module_changed,
		"lines": granted,
	}
