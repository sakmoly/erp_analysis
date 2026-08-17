"""Grant Delivery Note create/submit to Printechs warehouse desk roles."""

from __future__ import annotations

import frappe

WAREHOUSE_DN_PERMS = (
	("Printechs Warehouse Coordinator", {"read": 1, "write": 1, "create": 1, "submit": 1, "cancel": 0}),
	("Printechs Warehouse Manager", {"read": 1, "write": 1, "create": 1, "submit": 1, "cancel": 1}),
	("Printechs Warehouse User", {"read": 1, "write": 1, "create": 1, "submit": 1, "cancel": 0}),
)


def _upsert_custom_docperm(doctype: str, role: str, perms: dict[str, int]) -> bool:
	existing = frappe.db.get_value(
		"Custom DocPerm",
		{"parent": doctype, "role": role},
		"name",
	)
	if existing:
		doc = frappe.get_doc("Custom DocPerm", existing)
	else:
		doc = frappe.new_doc("Custom DocPerm")
		doc.parent = doctype
		doc.parenttype = "DocType"
		doc.parentfield = "permissions"
		doc.role = role
		doc.permlevel = 0

	changed = False
	for key, value in perms.items():
		if int(doc.get(key) or 0) != int(value):
			doc.set(key, int(value))
			changed = True

	if changed or doc.is_new():
		doc.flags.ignore_permissions = True
		doc.save(ignore_permissions=True)
		return True
	return False


def execute():
	if not frappe.db.exists("DocType", "Delivery Note"):
		return

	updated = 0
	for role, perms in WAREHOUSE_DN_PERMS:
		if not frappe.db.exists("Role", role):
			continue
		if _upsert_custom_docperm("Delivery Note", role, perms):
			updated += 1

	if updated:
		frappe.clear_cache(doctype="Delivery Note")
		frappe.logger().info(f"sync_warehouse_desk_dn_permissions: updated {updated} role(s)")
