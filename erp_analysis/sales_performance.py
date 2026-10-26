"""Phase 3B′ — Salesperson and product performance (actuals only; no targets)."""

from __future__ import annotations

from typing import Optional

import frappe
from frappe import _

from erp_analysis.access_context import (
	get_authenticated_access_context,
	guard_mobile_api,
	has_module_access,
	require_module_access,
	resolve_view_territory_scope,
)
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
	ctx = guard_mobile_api(company=company, module_key="sales_performance", scope_module="sales")
	company = ctx["company"]
	territories = ctx["view_territory_scope"]
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
			territories=territories,
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
	level: Optional[str] = None,
	item_code: Optional[str] = None,
	brand: Optional[str] = None,
	territory: Optional[str] = None,
	territories: Optional[str] = None,
	**kwargs,
):
	"""
	Product ranking by item, item group, or brand.

	Uses SalesDashBoard when available; falls back to Sales Invoice Item lines.
	"""
	# Sales dashboard drill fallback — same module gate as division widgets (`sales`).
	ctx = guard_mobile_api(
		company=company,
		module_key="sales",
		scope_module="sales",
		territory=_get_arg("territory", territory),
	)
	company = ctx["company"]
	user = ctx["user"]
	territory = _get_arg("territory", territory)
	territories_param = _get_arg("territories", territories)
	view_territories = resolve_view_territory_scope(
		requested=territory,
		requested_list=territories_param,
		user=user,
		company=company,
		module="sales",
	)
	group_by = _get_arg("group_by", group_by)
	level = (_get_arg("level", level) or "").strip().lower()
	if not group_by and level:
		if level in ("item_group", "sub_group", "group"):
			group_by = "item_group"
		elif level == "item":
			group_by = "item"
		elif level == "brand":
			group_by = "brand"
	group_by = group_by or "brand"
	item_code = (_get_arg("item_code", item_code) or "").strip() or None
	brand = _get_arg("brand", brand)
	period = _get_arg("period", period)
	from_date = _get_date_arg("from_date", "fromDate", default=from_date)
	to_date = _get_date_arg("to_date", "toDate", default=to_date)
	limit = _to_int(_get_arg("limit", limit), 20)
	division = _get_arg("division", kwargs.get("division"))
	if isinstance(division, str) and division.strip():
		division = [division.strip()]
	sub_group = _get_arg("sub_group", kwargs.get("sub_group") or kwargs.get("item_group"))
	if isinstance(sub_group, str) and sub_group.strip():
		sub_group = [sub_group.strip()]

	if division is None or sub_group is None:
		from erp_analysis.services.analytics_dimensions import parse_logical_filters

		raw_filters = _get_arg("filters", kwargs.get("filters"))
		parsed = parse_logical_filters(raw_filters) if raw_filters is not None else {}
		if division is None and parsed.get("division"):
			division = parsed["division"]
		if sub_group is None:
			sub_group = parsed.get("sub_group") or parsed.get("item_group")
		if division is None or sub_group is None:
			stack = _get_arg("drill_crumbs", kwargs.get("drill_crumbs"))
			if stack:
				parsed_crumbs = parse_logical_filters(
					{
						(e.get("dimension") or e.get("key") or "").strip().lower(): [e.get("value") or e.get("label")]
						for e in (stack if isinstance(stack, list) else [])
						if isinstance(e, dict) and (e.get("dimension") or e.get("key"))
					}
				)
				if division is None and parsed_crumbs.get("division"):
					division = parsed_crumbs["division"]
				if sub_group is None:
					sub_group = parsed_crumbs.get("sub_group") or parsed_crumbs.get("item_group")

	if isinstance(division, str) and division.strip():
		division = [division.strip()]

	try:
		if level == "item" and item_code:
			return sales_performance_service.get_item_product_performance(
				company=company,
				item_code=item_code,
				period=period,
				from_date=from_date,
				to_date=to_date,
				brand=brand,
				territories=view_territories,
			)
		return sales_performance_service.get_product_ranking(
			company=company,
			group_by=group_by,
			period=period,
			from_date=from_date,
			to_date=to_date,
			limit=limit,
			territories=view_territories,
			division=division,
			sub_group=sub_group,
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
	level: Optional[str] = None,
	item_code: Optional[str] = None,
	brand: Optional[str] = None,
	territory: Optional[str] = None,
	territories: Optional[str] = None,
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
		level=level,
		item_code=item_code,
		brand=brand,
		territory=territory,
		territories=territories,
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
	"""Sold qty and sales value for one item (days-of-supply helper)."""
	territory_arg = _get_arg("territory", territory)
	ctx = get_authenticated_access_context(company=company)
	user = ctx["user"]
	company = ctx["company"]
	# Stock item screens call this without opening Product Performance module.
	if not any(
		has_module_access(key, user=user, company=company)
		for key in ("sales_performance", "sales", "inventory")
	):
		require_module_access("sales_performance", user=user, company=company)

	from erp_analysis.access_context import require_object_access

	for object_key in (
		"erp_analysis.sales.get_item_sales_qty",
		"erp_analysis.sales_performance.get_item_sales_qty",
	):
		try:
			require_object_access(object_key, user=user, company=company, territory=territory_arg)
			break
		except frappe.PermissionError:
			continue
	else:
		require_object_access(
			"erp_analysis.sales.get_item_sales_qty",
			user=user,
			company=company,
			territory=territory_arg,
		)
	item_code = (_get_arg("item_code", item_code) or "").strip()
	if not item_code:
		frappe.throw(_("item_code is required"))
	territory = _get_arg("territory", territory)
	territories_param = _get_arg("territories", territories)
	view_territories = resolve_view_territory_scope(
		requested=territory,
		requested_list=territories_param,
		user=user,
		company=company,
		module="sales",
	)
	period = _get_arg("period", period)
	from_date = _get_date_arg("from_date", "fromDate", default=from_date)
	to_date = _get_date_arg("to_date", "toDate", default=to_date)

	brand = _get_arg("brand", brand)

	try:
		return sales_performance_service.get_item_sales_qty(
			company=company,
			item_code=item_code,
			period=period,
			from_date=from_date,
			to_date=to_date,
			brand=brand,
			territory=territory,
			territories=view_territories,
		)
	except Exception:
		frappe.log_error(title="sales_performance.get_item_sales_qty", message=frappe.get_traceback())
		try:
			start, end = sales_performance_service._period_bounds(period, from_date, to_date)
		except Exception:
			start, end = sales_performance_service._period_bounds(None, from_date, to_date)
		return {
			"item_code": item_code,
			"from_date": str(start),
			"to_date": str(end),
			"qty_sold": 0.0,
			"sales_value": 0.0,
			"qty": 0.0,
			"sales_qty": 0.0,
			"quantity_sold": 0.0,
		}


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
	ctx = guard_mobile_api(company=company, module_key="sales_performance", scope_module="sales")
	company = ctx["company"]
	territories = ctx["view_territory_scope"]
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
			territories=territories,
		)
	except Exception:
		frappe.log_error(title="sales_performance.get_salesperson_invoices", message=frappe.get_traceback())
		return {
			"salesperson": salesperson or "",
			"period": {"from_date": from_date, "to_date": to_date},
			"rows": [],
			"pagination": {"limit": limit, "offset": offset, "count": 0},
		}
