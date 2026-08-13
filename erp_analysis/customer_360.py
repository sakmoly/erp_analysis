"""Phase 3C — Customer 360 view."""

from __future__ import annotations

from typing import Optional

import frappe

from erp_analysis.access_context import assert_customer_in_view_scope, guard_mobile_api
from erp_analysis.services import customer_360 as customer_360_service
from erp_analysis.utils.rpc import get_arg as _get_arg, resolve_customer_id, to_int as _to_int


@frappe.whitelist(methods=["GET", "POST"], allow_guest=False)
def get_customer_360(
	company: Optional[str] = None,
	customer=None,
	from_date: Optional[str] = None,
	to_date: Optional[str] = None,
	invoice_limit: Optional[int] = None,
	open_so_limit: Optional[int] = None,
):
	"""Customer 360 — Phase 3C mobile contract (same payload as customer.get_customer_360)."""
	ctx = guard_mobile_api(company=company, module_key="customer_360", scope_module="sales")
	company = ctx["company"]
	customer_id = resolve_customer_id(_get_arg("customer", customer))
	from_date = _get_arg("from_date", from_date)
	to_date = _get_arg("to_date", to_date)
	invoice_limit = _to_int(_get_arg("invoice_limit", invoice_limit), 10)
	open_so_limit = _to_int(_get_arg("open_so_limit", open_so_limit), 10)

	if not customer_id:
		frappe.throw("Customer is required", frappe.MandatoryError)

	assert_customer_in_view_scope(customer_id, user=ctx["user"], company=company)

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
		frappe.log_error(title="customer_360.get_customer_360", message=frappe.get_traceback())
		return customer_360_service.empty_customer_360_payload(
			company=company,
			customer_id=customer_id,
			from_date=from_date,
			to_date=to_date,
			open_so_limit=open_so_limit,
		)


@frappe.whitelist(methods=["GET", "POST"], allow_guest=False)
def get_customer(customer: Optional[str] = None, **kwargs):
	"""Mobile-friendly Customer read — avoids /api/resource/Customer 403 for app users."""
	ctx = guard_mobile_api(module_key="customer_360", scope_module="sales")
	customer_id = resolve_customer_id(_get_arg("customer", customer) or kwargs.get("name"))
	if not customer_id:
		frappe.throw("Customer is required", frappe.MandatoryError)
	assert_customer_in_view_scope(customer_id, user=ctx["user"], company=ctx["company"])
	return customer_360_service.get_customer_object(customer_id)
