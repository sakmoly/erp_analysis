"""Ensure Delivery Note Set Source Warehouse is always set.

With Strict User Permissions, an empty set_warehouse hides the DN from lists
even when item warehouses are filled. Restore previous behaviour: always default
the header warehouse before validate/save.
"""

from __future__ import annotations

import frappe


def before_validate(doc, method=None):
	ensure_set_warehouse(doc)


def ensure_set_warehouse(doc):
	"""Fill set_warehouse when blank (user default → first item warehouse)."""
	if doc.get("set_warehouse"):
		return

	warehouse = (doc.get("user_default_warehouse") or "").strip() or None

	if not warehouse:
		user = frappe.session.user
		if user and user not in ("Guest", "Administrator"):
			warehouse = frappe.db.get_value("User", user, "default_warehouse")

	if not warehouse:
		for row in doc.get("items") or []:
			wh = (row.get("warehouse") or "").strip()
			if wh:
				warehouse = wh
				break

	if warehouse:
		doc.set_warehouse = warehouse
