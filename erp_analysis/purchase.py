"""Phase 3G — Purchase performance and open purchase orders."""

from __future__ import annotations

from typing import Optional

import frappe

from erp_analysis.services import purchase as purchase_service
from erp_analysis.utils.rpc import get_arg as _get_arg, to_int as _to_int


def _as_bool(value) -> bool:
	if isinstance(value, bool):
		return value
	if value is None:
		return False
	return str(value).lower() in ("1", "true", "yes")


@frappe.whitelist(methods=["GET", "POST"], allow_guest=False)
def get_purchase_dashboard(
	company: Optional[str] = None,
	limit: Optional[int] = None,
):
	"""Purchase dashboard — open PO count/value, pending receipt, breakdowns."""
	company = _get_arg("company", company) or frappe.defaults.get_user_default("Company")
	limit = _to_int(_get_arg("limit", limit), 10)

	try:
		return purchase_service.get_purchase_dashboard_payload(company=company, limit=limit)
	except Exception:
		frappe.log_error(title="purchase.get_purchase_dashboard", message=frappe.get_traceback())
		return {
			"kpis": {
				"open_count": 0,
				"open_value": 0,
				"pending_receipt_count": 0,
				"pending_receipt_value": 0,
				"to_bill_count": 0,
				"overdue_receipt_count": 0,
			},
			"by_status": [],
			"by_supplier": [],
		}


@frappe.whitelist(methods=["GET", "POST"], allow_guest=False)
def get_open_purchase_orders(
	company: Optional[str] = None,
	status: Optional[str] = None,
	pending_receipt_only: Optional[bool] = None,
	limit: Optional[int] = None,
	offset: Optional[int] = None,
):
	"""Paginated list of open purchase orders."""
	company = _get_arg("company", company) or frappe.defaults.get_user_default("Company")
	status = _get_arg("status", status)
	pending_receipt_only = _as_bool(_get_arg("pending_receipt_only", pending_receipt_only))
	limit = _to_int(_get_arg("limit", limit), 50)
	offset = _to_int(_get_arg("offset", offset), 0)

	try:
		return purchase_service.get_open_purchase_orders(
			company=company,
			status=status,
			pending_receipt_only=pending_receipt_only,
			limit=limit,
			offset=offset,
		)
	except Exception:
		frappe.log_error(title="purchase.get_open_purchase_orders", message=frappe.get_traceback())
		return {"rows": [], "pagination": {"total": 0, "limit": limit, "offset": offset}}
