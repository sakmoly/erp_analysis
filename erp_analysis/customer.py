"""Mobile customer module — search + Customer 360 contract paths (Phase 3C)."""

from __future__ import annotations

from typing import Optional

import frappe

from erp_analysis.services import customer_360 as customer_360_service
from erp_analysis.utils.rpc import get_arg as _get_arg, resolve_customer_id, to_int as _to_int


def _require_customer_360_access():
	from erp_analysis.permissions.customer import _user_has_customer_360_access

	if not _user_has_customer_360_access():
		frappe.throw("Not permitted to access Customer 360", frappe.PermissionError)


def _format_search_row(row: dict) -> dict:
	return {
		"id": row.get("name") or row.get("id"),
		"customer_name": row.get("customer_name") or row.get("name") or "",
		"territory": row.get("territory") or "",
		"customer_group": row.get("customer_group") or "",
		"mobile_no": row.get("mobile_no") or "",
		"email_id": row.get("email_id") or "",
	}


@frappe.whitelist(methods=["GET", "POST"], allow_guest=False)
def search_customers(
	query: Optional[str] = None,
	q: Optional[str] = None,
	territory: Optional[str] = None,
	limit: Optional[int] = None,
	offset: Optional[int] = None,
):
	"""Search customers by name/id for Customer 360 entry screen."""
	_require_customer_360_access()

	text = (_get_arg("query", query) or _get_arg("q", q) or "").strip()
	territory = _get_arg("territory", territory)
	limit = _to_int(_get_arg("limit", limit), 20)
	offset = _to_int(_get_arg("offset", offset), 0)

	filters: dict = {"disabled": 0}
	if territory:
		filters["territory"] = territory

	or_filters = None
	if text:
		or_filters = [
			["name", "like", f"%{text}%"],
			["customer_name", "like", f"%{text}%"],
			["mobile_no", "like", f"%{text}%"],
			["email_id", "like", f"%{text}%"],
		]

	from erp_analysis.permissions.customer import _customer_get_list_kwargs, _company_for_user

	list_kwargs = _customer_get_list_kwargs(
		frappe.session.user,
		_company_for_user(),
		filters=filters,
		or_filters=or_filters,
		fields=[
			"name",
			"customer_name",
			"territory",
			"customer_group",
			"mobile_no",
			"email_id",
		],
		limit_page_length=limit,
		limit_start=offset,
		order_by="modified desc",
	)

	rows = frappe.get_list("Customer", **list_kwargs)

	formatted = [_format_search_row(row) for row in rows]
	return {
		"rows": formatted,
		"pagination": {"limit": limit, "offset": offset, "count": len(formatted)},
	}


@frappe.whitelist(methods=["GET", "POST"], allow_guest=False)
def get_customer_360(
	company: Optional[str] = None,
	customer=None,
	from_date: Optional[str] = None,
	to_date: Optional[str] = None,
	invoice_limit: Optional[int] = None,
	open_so_limit: Optional[int] = None,
	**kwargs,
):
	"""Mobile path: erp_analysis.customer.get_customer_360 (Phase 3C contract)."""
	company = _get_arg("company", company) or frappe.defaults.get_user_default("Company")
	customer_raw = _get_arg("customer", customer) or kwargs.get("name")
	customer_id = resolve_customer_id(customer_raw)
	from_date = _get_arg("from_date", from_date)
	to_date = _get_arg("to_date", to_date)
	invoice_limit = _to_int(_get_arg("invoice_limit", invoice_limit), 10)
	open_so_limit = _to_int(_get_arg("open_so_limit", open_so_limit), 10)

	if not customer_id:
		frappe.throw("Customer is required", frappe.MandatoryError)

	try:
		return customer_360_service.get_customer_360_payload(
			company=company,
			customer=customer_id,
			from_date=from_date,
			to_date=to_date,
			invoice_limit=invoice_limit,
			open_so_limit=open_so_limit,
		)
	except frappe.MandatoryError:
		raise
	except Exception:
		frappe.log_error(title="customer.get_customer_360", message=frappe.get_traceback())
		return customer_360_service.empty_customer_360_payload(
			company=company,
			customer_id=customer_id,
			from_date=from_date,
			to_date=to_date,
			open_so_limit=open_so_limit,
		)


def _empty_customer_360_payload(
	company: Optional[str],
	customer_id: str,
	from_date: Optional[str],
	to_date: Optional[str],
	open_so_limit: int,
) -> dict:
	return customer_360_service.empty_customer_360_payload(
		company=company,
		customer_id=customer_id,
		from_date=from_date,
		to_date=to_date,
		open_so_limit=open_so_limit,
	)
