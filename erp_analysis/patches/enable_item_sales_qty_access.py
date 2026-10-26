"""Grant Item Sales Qty API on all enabled Access Profiles (days-of-supply)."""

from __future__ import annotations

import frappe

from erp_analysis.patches.sync_mobile_access_registry import ensure_registry_rows, sync_access_profiles
from erp_analysis.permissions.access_profile import clear_caches

OBJECT_KEYS = (
	"erp_analysis.sales.get_item_sales_qty",
	"erp_analysis.sales_performance.get_item_sales_qty",
)


def execute() -> None:
	if not frappe.db.exists("DocType", "Access Object Registry"):
		return

	key_to_name = ensure_registry_rows()
	sync_access_profiles(key_to_name)

	registry_names = [
		key_to_name[k]
		for k in OBJECT_KEYS
		if k in key_to_name
	]
	if not registry_names:
		return

	profiles = frappe.get_all("Access Profile", filters={"enabled": 1}, pluck="name")
	updated = 0

	for profile_name in profiles:
		profile = frappe.get_doc("Access Profile", profile_name)
		by_object: dict[str, object] = {
			row.access_object: row for row in profile.access_rules if row.access_object
		}
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
			updated += 1

	frappe.db.commit()
	clear_caches()
	frappe.logger("erp_analysis").info(
		"enable_item_sales_qty_access: ensured can_view on %s profile(s)", updated
	)
