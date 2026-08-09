"""Phase 3E — Sales Order / Order Book."""

from __future__ import annotations

from typing import Optional

import frappe

from erp_analysis.services import sales_orders as sales_orders_service
from erp_analysis.utils.rpc import get_arg as _get_arg, to_int as _to_int


def _as_bool(value) -> bool:
	if isinstance(value, bool):
		return value
	if value is None:
		return False
	return str(value).lower() in ("1", "true", "yes")


@frappe.whitelist(methods=["GET", "POST"], allow_guest=False)
def get_order_book_dashboard(
	company: Optional[str] = None,
	territory: Optional[str] = None,
	limit: Optional[int] = None,
):
	"""Order book dashboard — open SO count/value, pending delivery, breakdowns."""
	company = _get_arg("company", company) or frappe.defaults.get_user_default("Company")
	territory = _get_arg("territory", territory)
	limit = _to_int(_get_arg("limit", limit), 10)

	try:
		return sales_orders_service.get_order_book_dashboard_payload(
			company=company,
			territory=territory,
			limit=limit,
		)
	except Exception:
		frappe.log_error(title="sales_orders.get_order_book_dashboard", message=frappe.get_traceback())
		return {
			"kpis": {
				"open_count": 0,
				"open_value": 0,
				"pending_delivery_count": 0,
				"pending_delivery_value": 0,
				"to_bill_count": 0,
				"overdue_delivery_count": 0,
			},
			"by_status": [],
			"by_territory": [],
		}


@frappe.whitelist(methods=["GET", "POST"], allow_guest=False)
def get_open_sales_orders(
	company: Optional[str] = None,
	territory: Optional[str] = None,
	status: Optional[str] = None,
	pending_delivery_only: Optional[bool] = None,
	limit: Optional[int] = None,
	offset: Optional[int] = None,
):
	"""Paginated list of open sales orders."""
	company = _get_arg("company", company) or frappe.defaults.get_user_default("Company")
	territory = _get_arg("territory", territory)
	status = _get_arg("status", status)
	pending_delivery_only = _as_bool(_get_arg("pending_delivery_only", pending_delivery_only))
	limit = _to_int(_get_arg("limit", limit), 50)
	offset = _to_int(_get_arg("offset", offset), 0)

	try:
		return sales_orders_service.get_open_sales_orders(
			company=company,
			territory=territory,
			status=status,
			pending_delivery_only=pending_delivery_only,
			limit=limit,
			offset=offset,
		)
	except Exception:
		frappe.log_error(title="sales_orders.get_open_sales_orders", message=frappe.get_traceback())
		return {"rows": [], "pagination": {"total": 0, "limit": limit, "offset": offset}}


@frappe.whitelist(methods=["GET", "POST"], allow_guest=False)
def get_sales_order_dashboard(
	company: Optional[str] = None,
	territory: Optional[str] = None,
	limit: Optional[int] = None,
	**kwargs,
):
	"""Mobile path: erp_analysis.sales_orders.get_sales_order_dashboard"""
	return get_order_book_dashboard(company=company, territory=territory, limit=limit)
