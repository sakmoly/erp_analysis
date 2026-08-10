"""Schema-safe helpers for multi-site ERPNext (Printechs vs client schemas)."""

from __future__ import annotations

from typing import Optional, Sequence

import frappe


def has_field(doctype: str, fieldname: str) -> bool:
	"""True if field exists on DocType meta (standard or Custom Field)."""
	if not fieldname:
		return False
	if fieldname == "name":
		return True
	try:
		return bool(frappe.get_meta(doctype).has_field(fieldname))
	except Exception:
		return False


def has_column(doctype: str, fieldname: str) -> bool:
	"""True if physical DB column exists (use for raw SQL SELECT/WHERE)."""
	if not fieldname:
		return False
	if fieldname == "name":
		return True
	try:
		return bool(frappe.db.has_column(doctype, fieldname))
	except Exception:
		return False


def existing_fields(doctype: str, fields: Sequence[str]) -> list[str]:
	"""Return fieldnames that exist on DocType meta (standard or custom).

	``name`` is always kept when requested — it is the primary key and is not
	listed as a normal meta field on most DocTypes.
	"""
	return [f for f in fields if has_field(doctype, f)]


def existing_columns(doctype: str, fields: Sequence[str]) -> list[str]:
	"""Return fieldnames that exist as DB columns (safer for raw SELECT)."""
	return [f for f in fields if has_column(doctype, f)]


def sql_select(
	doctype: str,
	alias: str,
	fieldname: str,
	*,
	as_name: Optional[str] = None,
	coalesce: Optional[str] = None,
	missing: str = "NULL",
) -> str:
	"""Build a SELECT fragment that is safe when the column is absent.

	Examples::
	    sql_select("Delivery Note", "dn", "workflow_state")
	    # -> "dn.workflow_state AS workflow_state" or "NULL AS workflow_state"

	    sql_select("Delivery Note", "dn", "total_qty", coalesce="0")
	    # -> "COALESCE(dn.total_qty, 0) AS total_qty" or "0 AS total_qty"
	"""
	col = as_name or fieldname
	if has_column(doctype, fieldname):
		expr = f"`{alias}`.`{fieldname}`"
		if coalesce is not None:
			return f"COALESCE({expr}, {coalesce}) AS `{col}`"
		return f"{expr} AS `{col}`"
	if coalesce is not None:
		return f"{coalesce} AS `{col}`"
	return f"{missing} AS `{col}`"


def safe_get_value(
	doctype: str,
	name: str,
	fields: Sequence[str],
	*,
	as_dict: bool = True,
):
	"""get_value limited to fields present on meta (avoids Unknown column)."""
	safe = existing_fields(doctype, fields)
	if not safe:
		return {} if as_dict else None
	return frappe.db.get_value(doctype, name, safe, as_dict=as_dict)


def customer_credit_limit(customer: str, company: Optional[str] = None) -> float:
	"""Credit limit for Customer — child table first, parent column only if present.

	Modern ERPNext uses ``credit_limits`` (Customer Credit Limit). Some sites still
	have a legacy/custom ``Customer.credit_limit`` column; Ozdah may have neither.
	"""
	if not customer:
		return 0.0

	meta = frappe.get_meta("Customer")
	if meta.has_field("credit_limits") and frappe.db.exists("DocType", "Customer Credit Limit"):
		filters: dict = {"parent": customer, "parenttype": "Customer"}
		if company:
			filters["company"] = company
		rows = frappe.get_all(
			"Customer Credit Limit",
			filters=filters,
			fields=["credit_limit"],
			ignore_permissions=True,
		)
		if not rows and company:
			# Fall back to any company row if exact company missing
			rows = frappe.get_all(
				"Customer Credit Limit",
				filters={"parent": customer, "parenttype": "Customer"},
				fields=["credit_limit"],
				ignore_permissions=True,
			)
		if rows:
			return float(max((r.get("credit_limit") or 0) for r in rows))

	if frappe.db.has_column("Customer", "credit_limit"):
		val = frappe.db.get_value("Customer", customer, "credit_limit")
		return float(val or 0)

	return 0.0
