"""Mobile sales module — contract aliases for performance APIs."""

from __future__ import annotations

from typing import Any, Optional

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
	level: Optional[str] = None,
	item_code: Optional[str] = None,
	brand: Optional[str] = None,
	territory: Optional[str] = None,
	territories: Optional[str] = None,
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
		level=level,
		item_code=item_code,
		brand=brand,
		territory=territory,
		territories=territories,
		**kwargs,
	)


@frappe.whitelist(methods=["GET", "POST"], allow_guest=False)
def get_sales_by_division_drill(
	company: Optional[str] = None,
	period: Optional[str] = None,
	from_date: Optional[str] = None,
	to_date: Optional[str] = None,
	limit: Optional[int] = None,
	drill_depth: Optional[int] = None,
	dimension: Optional[str] = None,
	filters: Any = None,
	division: Any = None,
	sub_group: Any = None,
	**kwargs,
):
	"""Mobile path: division → item group → brand (SalesDashBoard only)."""
	from erp_analysis.services.sales_drill import get_sales_by_division_drill as _impl

	return _impl(
		company=company,
		period=period,
		from_date=from_date,
		to_date=to_date,
		limit=limit,
		drill_depth=drill_depth,
		dimension=dimension,
		filters=filters,
		division=division,
		sub_group=sub_group,
		**kwargs,
	)


@frappe.whitelist(methods=["GET", "POST"], allow_guest=False)
def get_item_sales_qty(
	company: Optional[str] = None,
	item_code: Optional[str] = None,
	period: Optional[str] = None,
	from_date: Optional[str] = None,
	to_date: Optional[str] = None,
	brand: Optional[str] = None,
	territory: Optional[str] = None,
	territories: Optional[str] = None,
	**kwargs,
):
	"""Mobile path: erp_analysis.sales.get_item_sales_qty"""
	from erp_analysis.sales_performance import get_item_sales_qty as _impl

	return _impl(
		company=company,
		item_code=item_code,
		period=period,
		from_date=from_date,
		to_date=to_date,
		brand=brand,
		territory=territory,
		territories=territories,
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
