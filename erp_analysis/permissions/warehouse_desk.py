"""Desk warehouse roles — SO→DN warehouse User Permission bypass.

With Strict User Permissions, Delivery Note Item.warehouse must match User Permission.
Sales Orders often mix warehouses (e.g. Riyadh user, Jeddah lines). Users with warehouse
desk roles may use warehouses that appear on Sales Order lines they can read.
"""

from __future__ import annotations

import frappe

WAREHOUSE_DESK_ROLES = frozenset(
	{
		"Printechs Warehouse Coordinator",
		"Printechs Warehouse Manager",
		"Printechs Warehouse User",
	}
)

_WAREHOUSE_ITEM_DOCTYPES = frozenset(
	{
		"Delivery Note Item",
		"Sales Order Item",
		"Sales Invoice Item",
	}
)


def _user_has_warehouse_desk_role(user: str | None = None) -> bool:
	user = user or frappe.session.user
	if not user or user in ("Guest", "Administrator"):
		return user == "Administrator"
	return bool(set(frappe.get_roles(user)) & WAREHOUSE_DESK_ROLES)


def _warehouse_on_readable_sales_order(user: str, warehouse: str, doc) -> bool:
	"""True when warehouse is set on a Sales Order line the user can read."""
	if not warehouse or not doc:
		return False

	so_detail = doc.get("so_detail")
	if so_detail:
		row = frappe.db.get_value(
			"Sales Order Item",
			so_detail,
			["warehouse", "parent"],
			as_dict=True,
		)
		if row and row.warehouse == warehouse and row.parent:
			return frappe.has_permission("Sales Order", "read", doc=row.parent, user=user)

	against_so = doc.get("against_sales_order")
	if against_so:
		match = frappe.db.exists(
			"Sales Order Item",
			{"parent": against_so, "warehouse": warehouse},
		)
		if match and frappe.has_permission("Sales Order", "read", doc=against_so, user=user):
			return True

	parent = doc.get("parent")
	parenttype = doc.get("parenttype")
	if parenttype == "Delivery Note" and parent:
		so_names = frappe.get_all(
			"Delivery Note Item",
			filters={"parent": parent, "warehouse": warehouse},
			pluck="against_sales_order",
		)
		for so_name in {n for n in so_names if n}:
			if frappe.has_permission("Sales Order", "read", doc=so_name, user=user):
				return True

	return False


def patch_warehouse_desk_user_permission():
	import frappe.permissions as permissions_module

	if getattr(permissions_module, "_erp_analysis_warehouse_desk_patched", False):
		return

	original = permissions_module.has_user_permission

	def has_user_permission(doc, user=None, debug=False, ptype=None):
		if (
			doc
			and not isinstance(doc, str)
			and getattr(doc, "doctype", None) in _WAREHOUSE_ITEM_DOCTYPES
			and ptype in (None, "read", "write", "create", "submit")
			and _user_has_warehouse_desk_role(user)
		):
			warehouse = doc.get("warehouse") or doc.get("target_warehouse")
			if warehouse and _warehouse_on_readable_sales_order(user or frappe.session.user, warehouse, doc):
				return True

		return original(doc, user=user, debug=debug, ptype=ptype)

	permissions_module.has_user_permission = has_user_permission
	permissions_module._erp_analysis_warehouse_desk_patched = True


def apply_warehouse_desk_permission_patch():
	patch_warehouse_desk_user_permission()
