"""Allow empty Territory / DN header warehouses while Strict UP stays On.

Empty link values are treated as OK for specific fields only.
Non-empty values must still match User Permission (other territories blocked).
List filters are unchanged (no ignore_user_permissions on Territory).
"""

from __future__ import annotations

import frappe
from frappe.permissions import get_allowed_docs_for_doctype

# Parent doctype → fields that may be blank under Strict UP
ALLOW_EMPTY_LINK_FIELDS = {
	"Sales Order": frozenset({"territory"}),
	"Sales Invoice": frozenset({"territory"}),
	"Delivery Note": frozenset({"territory", "set_warehouse", "user_default_warehouse"}),
	# Item row warehouse often blank until packed; still enforce when set
	"Delivery Note Item": frozenset({"warehouse", "target_warehouse"}),
	"Stock Entry": frozenset({"from_warehouse", "to_warehouse", "user_default_warehouse"}),
	"Stock Entry Detail": frozenset({"s_warehouse", "t_warehouse"}),
}

_patched = False


def apply_strict_empty_link_patch():
	"""Wrap frappe.permissions.has_user_permission once per process."""
	global _patched
	if _patched:
		return

	import frappe.permissions as perm_mod

	original = perm_mod.has_user_permission

	def has_user_permission(doc, user=None, debug=False, ptype=None):
		saved = []
		try:
			if (
				doc is not None
				and not isinstance(doc, str)
				and frappe.get_system_settings("apply_strict_user_permissions")
			):
				_fill_empty_allowed_links(doc, user, saved)
				# Children are checked inside original(); fill those too
				if hasattr(doc, "get_all_children"):
					for child in doc.get_all_children():
						_fill_empty_allowed_links(child, user, saved)

			return original(doc, user=user, debug=debug, ptype=ptype)
		finally:
			for d, fieldname, previous in saved:
				d.set(fieldname, previous)

	perm_mod.has_user_permission = has_user_permission
	_patched = True


def _fill_empty_allowed_links(doc, user, saved: list):
	"""During the permission check only, replace blank allowed-empty fields
	with the user's first permitted value so Strict UP does not treat them as 'empty'.
	"""
	doctype = doc.get("doctype")
	allow_fields = ALLOW_EMPTY_LINK_FIELDS.get(doctype)
	if not allow_fields:
		return

	from frappe.core.doctype.user_permission.user_permission import get_user_permissions

	user_permissions = get_user_permissions(user or frappe.session.user)
	if not user_permissions:
		return

	# Parent doctype for applicable_for is the top-level doc
	parent_dt = doc.get("parenttype") or doctype

	for fieldname in allow_fields:
		if doc.get(fieldname):
			continue
		df = doc.meta.get_field(fieldname) if getattr(doc, "meta", None) else None
		if not df or getattr(df, "ignore_user_permissions", 0):
			continue
		options = df.options
		if options not in user_permissions:
			continue
		allowed = get_allowed_docs_for_doctype(user_permissions.get(options, []), parent_dt)
		if not allowed:
			continue
		saved.append((doc, fieldname, doc.get(fieldname)))
		doc.set(fieldname, allowed[0])


def ensure_strict_empty_link_patch():
	"""Safe to call from before_request (idempotent)."""
	apply_strict_empty_link_patch()
