"""Mobile sales module — contract aliases for performance APIs."""

from __future__ import annotations

from typing import Optional

import frappe


@frappe.whitelist(methods=["GET", "POST"], allow_guest=False)
def get_salesperson_performance(
	company: Optional[str] = None,
	period: Optional[str] = None,
	from_date: Optional[str] = None,
	to_date: Optional[str] = None,
	limit: Optional[int] = None,
	**kwargs,
):
	"""Mobile path: erp_analysis.sales.get_salesperson_performance"""
	from erp_analysis.sales_performance import get_salesperson_performance as _impl

	return _impl(
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
	"""Mobile path: erp_analysis.sales.get_product_performance"""
	from erp_analysis.sales_performance import get_product_performance as _impl

	return _impl(
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
	"""Mobile path: erp_analysis.sales.get_salesperson_invoices"""
	from erp_analysis.sales_performance import get_salesperson_invoices as _impl

	return _impl(
		company=company,
		salesperson=salesperson,
		from_date=from_date,
		to_date=to_date,
		limit=limit,
		offset=offset,
	)
