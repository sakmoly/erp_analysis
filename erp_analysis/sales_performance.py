"""Phase 3B′ — Salesperson and product performance (actuals only; no targets)."""

from __future__ import annotations

from typing import Optional

import frappe

from erp_analysis.services import sales_performance as sales_performance_service
from erp_analysis.utils.rpc import get_arg as _get_arg, get_date_arg as _get_date_arg, to_int as _to_int


@frappe.whitelist(methods=["GET", "POST"], allow_guest=False)
def get_salesperson_ranking(
	company: Optional[str] = None,
	period: Optional[str] = None,
	from_date: Optional[str] = None,
	to_date: Optional[str] = None,
	limit: Optional[int] = None,
):
	"""
	Salesperson ranking by actual sales (MTD/YTD/today or custom date range).

	Uses SalesDashBoard.Sales_Person when available; falls back to Sales Team / invoice owner.
	"""
	company = _get_arg("company", company) or frappe.defaults.get_user_default("Company")
	period = _get_arg("period", period)
	from_date = _get_date_arg("from_date", "fromDate", default=from_date)
	to_date = _get_date_arg("to_date", "toDate", default=to_date)
	limit = _to_int(_get_arg("limit", limit), 20)

	try:
		return sales_performance_service.get_salesperson_ranking(
			company=company,
			period=period,
			from_date=from_date,
			to_date=to_date,
			limit=limit,
		)
	except Exception:
		frappe.log_error(title="sales_performance.get_salesperson_ranking", message=frappe.get_traceback())
		return {"period": {"from_date": from_date, "to_date": to_date}, "rows": []}


@frappe.whitelist(methods=["GET", "POST"], allow_guest=False)
def get_product_ranking(
	company: Optional[str] = None,
	group_by: Optional[str] = None,
	period: Optional[str] = None,
	from_date: Optional[str] = None,
	to_date: Optional[str] = None,
	limit: Optional[int] = None,
):
	"""
	Product ranking by item, item group, or brand.

	Uses SalesDashBoard when available; falls back to Sales Invoice Item lines.
	"""
	company = _get_arg("company", company) or frappe.defaults.get_user_default("Company")
	group_by = _get_arg("group_by", group_by) or "brand"
	period = _get_arg("period", period)
	from_date = _get_arg("from_date", from_date)
	to_date = _get_arg("to_date", to_date)
	limit = _to_int(_get_arg("limit", limit), 20)

	try:
		return sales_performance_service.get_product_ranking(
			company=company,
			group_by=group_by,
			period=period,
			from_date=from_date,
			to_date=to_date,
			limit=limit,
		)
	except Exception:
		frappe.log_error(title="sales_performance.get_product_ranking", message=frappe.get_traceback())
		return {
			"group_by": group_by,
			"period": {"from_date": from_date, "to_date": to_date},
			"rows": [],
		}


@frappe.whitelist(methods=["GET", "POST"], allow_guest=False)
def get_salesperson_performance(
	company: Optional[str] = None,
	period: Optional[str] = None,
	from_date: Optional[str] = None,
	to_date: Optional[str] = None,
	limit: Optional[int] = None,
	**kwargs,
):
	"""Mobile contract name for salesperson ranking (actuals only; no targets)."""
	return get_salesperson_ranking(
		company=company,
		period=period,
		from_date=from_date,
		to_date=to_date,
		limit=limit,
	)


@frappe.whitelist(methods=["GET", "POST"], allow_guest=False)
def get_product_performance(
	company: Optional[str] = None,
	group_by: Optional[str] = None,
	period: Optional[str] = None,
	from_date: Optional[str] = None,
	to_date: Optional[str] = None,
	limit: Optional[int] = None,
	**kwargs,
):
	"""Mobile contract name for product ranking."""
	return get_product_ranking(
		company=company,
		group_by=group_by,
		period=period,
		from_date=from_date,
		to_date=to_date,
		limit=limit,
	)


@frappe.whitelist(methods=["GET", "POST"], allow_guest=False)
def get_salesperson_invoices(
	company: Optional[str] = None,
	salesperson: Optional[str] = None,
	from_date: Optional[str] = None,
	to_date: Optional[str] = None,
	limit: Optional[int] = None,
	offset: Optional[int] = None,
	**kwargs,
):
	"""Invoice list for salesperson drill-down (mobile-safe)."""
	company = _get_arg("company", company) or frappe.defaults.get_user_default("Company")
	salesperson = _get_arg("salesperson", salesperson) or kwargs.get("sales_person")
	from_date = _get_date_arg("from_date", "fromDate", default=from_date)
	to_date = _get_date_arg("to_date", "toDate", default=to_date)
	limit = _to_int(_get_arg("limit", limit), 50)
	offset = _to_int(_get_arg("offset", offset), 0)

	try:
		return sales_performance_service.get_salesperson_invoices(
			company=company,
			salesperson=salesperson,
			from_date=from_date,
			to_date=to_date,
			limit=limit,
			offset=offset,
		)
	except Exception:
		frappe.log_error(title="sales_performance.get_salesperson_invoices", message=frappe.get_traceback())
		return {
			"salesperson": salesperson or "",
			"period": {"from_date": from_date, "to_date": to_date},
			"rows": [],
			"pagination": {"limit": limit, "offset": offset, "count": 0},
		}
