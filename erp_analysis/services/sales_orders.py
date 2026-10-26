"""Open Sales Order queries for order book dashboard and executive KPIs."""

from __future__ import annotations

from typing import Any, Optional

import frappe

OPEN_SO_STATUSES = ("Closed", "Completed", "Cancelled", "Draft", "Stopped")
DATE_SCOPE_OPEN_SNAPSHOT = "open_snapshot"


def _company_sql(company: Optional[str], alias: str = "so") -> tuple[str, list[Any]]:
	if not company:
		return "", []
	return f" AND {alias}.company = %s", [company]


def _territory_sql(
	territory: Optional[str] = None,
	territories: Optional[list[str]] = None,
	alias: str = "so",
) -> tuple[str, list[Any]]:
	from erp_analysis.permissions.access_profile import si_territory_sql

	scope = territories
	if scope is None and territory:
		scope = [territory]
	return si_territory_sql(scope, field=f"{alias}.territory")


def _customer_sql(customer: Optional[str], alias: str = "so") -> tuple[str, list[Any]]:
	if not customer:
		return "", []
	return f" AND {alias}.customer = %s", [customer]


def resolve_open_so_territories(
	user: Optional[str],
	company: Optional[str],
	filters: Any = None,
	*,
	territory: Optional[str] = None,
	territories: Optional[list[str]] = None,
) -> Optional[list[str]]:
	"""Territory scope aligned with Sales dashboard (filters + view_all_sales)."""
	from erp_analysis.services.analytics_sales import company_wide_sales_view_for_filters
	from erp_analysis.services.module_kpis import _territory_scope_from_filters
	from erp_analysis.permissions.access_profile import resolve_territory_scope

	if territories is not None:
		return territories
	user = user or frappe.session.user
	if company_wide_sales_view_for_filters(user, company, filters):
		return None
	territory_one, territory_list = _territory_scope_from_filters(filters)
	if territory is None and territory_one:
		territory = territory_one
	if territory_list and not territory:
		return resolve_territory_scope(
			requested_list=territory_list,
			user=user,
			company=company,
			purpose="view",
			module="sales",
		)
	return resolve_territory_scope(
		requested=territory,
		user=user,
		company=company,
		purpose="view",
		module="sales",
	)


def _open_so_where(
	company: Optional[str] = None,
	territory: Optional[str] = None,
	customer: Optional[str] = None,
	alias: str = "so",
	territories: Optional[list[str]] = None,
	*,
	user: Optional[str] = None,
	filters: Any = None,
	pending_delivery_only: bool = False,
) -> tuple[str, list[Any]]:
	from erp_analysis.permissions.access_profile import resolve_territory_scope

	if territories is None and user is not None:
		territories = resolve_open_so_territories(user, company, filters, territory=territory)
	elif territories is None:
		territories = resolve_territory_scope(
			requested=territory, company=company, purpose="view", module="sales"
		)

	company_sql, company_params = _company_sql(company, alias)
	territory_sql, territory_params = _territory_sql(
		territory=None, territories=territories, alias=alias
	)
	customer_sql, customer_params = _customer_sql(customer, alias)
	pending_sql = f" AND {alias}.per_delivered < 100" if pending_delivery_only else ""
	where = f"""
		{alias}.docstatus = 1
		AND {alias}.status NOT IN ({", ".join("%s" for _ in OPEN_SO_STATUSES)})
		{pending_sql}
		{company_sql}
		{territory_sql}
		{customer_sql}
	"""
	params = [*OPEN_SO_STATUSES, *company_params, *territory_params, *customer_params]
	return where, params


def _delivery_status_label(per_delivered: float) -> str:
	per = float(per_delivered or 0)
	if per >= 100:
		return "Fully Delivered"
	if per <= 0:
		return "Not Delivered"
	return "Partially Delivered"


def _pending_delivery_value_expr(so_alias: str = "so") -> str:
	"""Approximate pending delivery amount from SO header (ERPNext % delivered)."""
	return f"""
		COALESCE({so_alias}.base_grand_total, 0)
		* GREATEST(100 - COALESCE({so_alias}.per_delivered, 0), 0) / 100
	"""


def get_open_so_summary(
	*,
	user: Optional[str] = None,
	company: Optional[str] = None,
	filters: Any = None,
	date_scope: str = DATE_SCOPE_OPEN_SNAPSHOT,
) -> dict[str, Any]:
	"""Open SO count + pending delivery value for mobile KPI (open_snapshot ignores dashboard dates)."""
	company = company or frappe.defaults.get_user_default("Company")
	user = user or frappe.session.user
	where, params = _open_so_where(
		company,
		user=user,
		filters=filters,
		pending_delivery_only=True,
	)
	pending_expr = _pending_delivery_value_expr("so")
	row = frappe.db.sql(
		f"""
		SELECT
			COUNT(*) AS open_so_count,
			COALESCE(SUM({pending_expr}), 0) AS open_so_value
		FROM `tabSales Order` so
		WHERE {where}
		""",
		tuple(params),
		as_dict=True,
	)[0]
	currency = frappe.get_cached_value("Company", company, "default_currency") if company else None
	return {
		"open_so_count": int(row.open_so_count or 0),
		"open_so_value": round(float(row.open_so_value or 0), 2),
		"currency": currency,
		"date_scope": date_scope or DATE_SCOPE_OPEN_SNAPSHOT,
	}


def get_order_book_summary(
	company: Optional[str] = None,
	territory: Optional[str] = None,
	territories: Optional[list[str]] = None,
) -> dict[str, Any]:
	"""Compact KPI block for executive dashboard."""
	company = company or frappe.defaults.get_user_default("Company")
	where, params = _open_so_where(
		company, territory=territory, territories=territories
	)

	row = frappe.db.sql(
		f"""
		SELECT
			COUNT(*) AS open_count,
			COALESCE(SUM(so.base_grand_total), 0) AS open_value,
			COALESCE(SUM(CASE WHEN so.per_delivered < 100 THEN 1 ELSE 0 END), 0) AS pending_delivery_count,
			COALESCE(SUM(
				CASE WHEN so.per_delivered < 100 THEN so.base_grand_total ELSE 0 END
			), 0) AS pending_delivery_value
		FROM `tabSales Order` so
		WHERE {where}
		""",
		tuple(params),
		as_dict=True,
	)[0]

	return {
		"open_count": int(row.open_count or 0),
		"open_value": round(float(row.open_value or 0), 2),
		"pending_delivery_count": int(row.pending_delivery_count or 0),
		"pending_delivery_value": round(float(row.pending_delivery_value or 0), 2),
	}


def get_order_book_by_status(
	company: Optional[str] = None,
	territory: Optional[str] = None,
	limit: int = 10,
) -> list[dict[str, Any]]:
	where, params = _open_so_where(company, territory)

	rows = frappe.db.sql(
		f"""
		SELECT
			so.status,
			COUNT(*) AS order_count,
			COALESCE(SUM(so.base_grand_total), 0) AS order_value
		FROM `tabSales Order` so
		WHERE {where}
		GROUP BY so.status
		ORDER BY order_value DESC
		LIMIT %s
		""",
		tuple([*params, int(limit)]),
		as_dict=True,
	)

	return [
		{
			"status": row.status,
			"order_count": int(row.order_count or 0),
			"order_value": round(float(row.order_value or 0), 2),
		}
		for row in rows
	]


def get_order_book_by_territory(
	company: Optional[str] = None,
	limit: int = 10,
) -> list[dict[str, Any]]:
	where, params = _open_so_where(company, territory=None)

	rows = frappe.db.sql(
		f"""
		SELECT
			COALESCE(so.territory, 'Unassigned') AS territory,
			COUNT(*) AS order_count,
			COALESCE(SUM(so.base_grand_total), 0) AS order_value,
			COALESCE(SUM(
				CASE WHEN so.per_delivered < 100 THEN so.base_grand_total ELSE 0 END
			), 0) AS pending_delivery_value
		FROM `tabSales Order` so
		WHERE {where}
		GROUP BY COALESCE(so.territory, 'Unassigned')
		ORDER BY order_value DESC
		LIMIT %s
		""",
		tuple([*params, int(limit)]),
		as_dict=True,
	)

	return [
		{
			"territory": row.territory,
			"order_count": int(row.order_count or 0),
			"order_value": round(float(row.order_value or 0), 2),
			"pending_delivery_value": round(float(row.pending_delivery_value or 0), 2),
		}
		for row in rows
	]


def get_order_book_dashboard_payload(
	company: Optional[str] = None,
	territory: Optional[str] = None,
	limit: int = 10,
) -> dict[str, Any]:
	summary = get_order_book_summary(company=company, territory=territory)
	where, params = _open_so_where(company, territory)

	extra = frappe.db.sql(
		f"""
		SELECT
			COALESCE(SUM(CASE WHEN so.per_billed < 100 THEN 1 ELSE 0 END), 0) AS to_bill_count,
			COALESCE(SUM(
				CASE WHEN so.delivery_date < CURDATE() AND so.per_delivered < 100 THEN 1 ELSE 0 END
			), 0) AS overdue_delivery_count
		FROM `tabSales Order` so
		WHERE {where}
		""",
		tuple(params),
		as_dict=True,
	)[0]

	kpis = {
		**summary,
		"to_bill_count": int(extra.to_bill_count or 0),
		"overdue_delivery_count": int(extra.overdue_delivery_count or 0),
	}

	return {
		"kpis": kpis,
		"by_status": get_order_book_by_status(company=company, territory=territory, limit=limit),
		"by_territory": get_order_book_by_territory(company=company, limit=limit),
	}


def _format_open_order_row(row: Any) -> dict[str, Any]:
	per = round(float(row.per_delivered or 0), 2)
	pending_val = round(float(row.pending_delivery_value or 0), 2)
	return {
		"sales_order": row.name,
		"name": row.name,
		"customer": row.customer,
		"customer_name": row.customer_name or row.customer,
		"territory": row.territory,
		"transaction_date": str(row.transaction_date) if row.transaction_date else None,
		"delivery_date": str(row.delivery_date) if row.delivery_date else None,
		"status": row.status,
		"per_delivered": per,
		"per_billed": round(float(row.per_billed or 0), 2),
		"grand_total": round(float(row.grand_total or 0), 2),
		"amount": round(float(row.grand_total or 0), 2),
		"pending_delivery_value": pending_val,
		"delivery_status": _delivery_status_label(per),
		"salesperson": row.salesperson or None,
	}


def list_open_sales_orders_for_drill(
	*,
	user: Optional[str] = None,
	company: Optional[str] = None,
	filters: Any = None,
	limit: int = 500,
	offset: int = 0,
	search: Optional[str] = None,
) -> dict[str, Any]:
	company = company or frappe.defaults.get_user_default("Company")
	user = user or frappe.session.user
	where, params = _open_so_where(
		company,
		user=user,
		filters=filters,
		pending_delivery_only=True,
	)
	pending_expr = _pending_delivery_value_expr("so")
	extra_sql = ""
	if search and str(search).strip():
		extra_sql = " AND (so.name LIKE %s OR so.customer_name LIKE %s OR so.customer LIKE %s)"
		like = f"%{str(search).strip()}%"
		params.extend([like, like, like])

	count_row = frappe.db.sql(
		f"""
		SELECT COUNT(*) AS total
		FROM `tabSales Order` so
		WHERE {where}
		{extra_sql}
		""",
		tuple(params),
		as_dict=True,
	)[0]
	total = int(count_row.total or 0)

	list_params = [*params, int(limit), int(offset)]
	rows = frappe.db.sql(
		f"""
		SELECT
			so.name,
			so.customer,
			so.customer_name,
			COALESCE(so.territory, '') AS territory,
			so.transaction_date,
			so.delivery_date,
			so.status,
			COALESCE(so.per_delivered, 0) AS per_delivered,
			COALESCE(so.per_billed, 0) AS per_billed,
			COALESCE(so.base_grand_total, 0) AS grand_total,
			({pending_expr}) AS pending_delivery_value,
			(
				SELECT st.sales_person
				FROM `tabSales Team` st
				WHERE st.parent = so.name
				ORDER BY st.allocated_percentage DESC
				LIMIT 1
			) AS salesperson
		FROM `tabSales Order` so
		WHERE {where}
		{extra_sql}
		ORDER BY pending_delivery_value DESC, so.transaction_date ASC, so.name ASC
		LIMIT %s OFFSET %s
		""",
		tuple(list_params),
		as_dict=True,
	)

	summary = get_open_so_summary(user=user, company=company, filters=filters)
	orders = [_format_open_order_row(row) for row in rows]
	return {
		"meta": {
			**summary,
			"total_rows": total,
		},
		"orders": orders,
	}


def get_open_sales_order_items(
	*,
	user: Optional[str] = None,
	company: Optional[str] = None,
	sales_order: Optional[str] = None,
	filters: Any = None,
	limit: int = 200,
	pending_lines_only: bool = True,
) -> dict[str, Any]:
	from erp_analysis.services.analytics_dimensions import parse_logical_filters

	if not sales_order:
		parsed = parse_logical_filters(filters)
		for val in parsed.get("sales_order") or []:
			text = str(val or "").strip()
			if text:
				sales_order = text
				break
	if not sales_order:
		frappe.throw(frappe._("sales_order is required"), frappe.ValidationError)

	company = company or frappe.defaults.get_user_default("Company")
	user = user or frappe.session.user
	if not frappe.db.exists("Sales Order", sales_order):
		frappe.throw(frappe._("Sales Order {0} not found").format(sales_order), frappe.ValidationError)

	header = frappe.db.get_value(
		"Sales Order",
		sales_order,
		[
			"company",
			"customer",
			"customer_name",
			"territory",
			"docstatus",
			"status",
			"per_delivered",
			"delivery_date",
			"transaction_date",
		],
		as_dict=True,
	)
	if company and header.company != company:
		frappe.throw(frappe._("Sales Order belongs to another company"), frappe.ValidationError)
	if int(header.docstatus or 0) != 1:
		frappe.throw(frappe._("Sales Order is not submitted"), frappe.ValidationError)

	territories = resolve_open_so_territories(user, company, filters)
	terr_sql, terr_params = _territory_sql(territories=territories)
	if terr_sql and header.territory:
		scope = territories or []
		if scope and header.territory not in scope:
			frappe.throw(frappe._("Sales Order is outside your territory scope"), frappe.PermissionError)

	pending_filter = ""
	if pending_lines_only:
		pending_filter = " AND (soi.qty - COALESCE(soi.delivered_qty, 0)) > 0"

	rows = frappe.db.sql(
		f"""
		SELECT
			soi.name AS so_detail,
			soi.item_code,
			soi.item_name,
			soi.qty,
			COALESCE(soi.delivered_qty, 0) AS delivered_qty,
			(soi.qty - COALESCE(soi.delivered_qty, 0)) AS pending_qty,
			COALESCE(soi.base_rate, soi.rate, 0) AS rate,
			(soi.qty - COALESCE(soi.delivered_qty, 0)) * COALESCE(soi.base_rate, soi.rate, 0) AS pending_amount,
			soi.uom,
			soi.warehouse,
			soi.delivery_date AS line_delivery_date
		FROM `tabSales Order Item` soi
		WHERE soi.parent = %s
		{pending_filter}
		ORDER BY soi.idx ASC
		LIMIT %s
		""",
		(sales_order, int(limit)),
		as_dict=True,
	)

	currency = frappe.get_cached_value("Company", company, "default_currency") if company else None
	header_delivery = (
		str(header.delivery_date) if getattr(header, "delivery_date", None) else None
	)
	items = []
	pending_total = 0.0
	for row in rows:
		line_delivery = row.line_delivery_date or header.delivery_date
		delivery_date = str(line_delivery) if line_delivery else header_delivery
		pending_amount = round(float(row.pending_amount or 0), 2)
		pending_total += pending_amount
		items.append(
			{
				"item_code": row.item_code,
				"item_name": row.item_name,
				"qty": float(row.qty or 0),
				"delivered_qty": float(row.delivered_qty or 0),
				"pending_qty": float(row.pending_qty or 0),
				"rate": round(float(row.rate or 0), 2),
				"pending_amount": pending_amount,
				"uom": row.uom,
				"warehouse": row.warehouse,
				"so_detail": row.so_detail,
				"delivery_date": delivery_date,
			}
		)
	return {
		"meta": {
			"sales_order": sales_order,
			"customer_name": header.customer_name or header.customer,
			"delivery_date": header_delivery,
			"currency": currency,
			"pending_delivery_value": round(pending_total, 2),
			"open_so_value": round(pending_total, 2),
			"line_count": len(items),
		},
		"items": items,
	}


def get_open_sales_orders(
	company: Optional[str] = None,
	territory: Optional[str] = None,
	customer: Optional[str] = None,
	status: Optional[str] = None,
	pending_delivery_only: bool = False,
	limit: int = 50,
	offset: int = 0,
	*,
	user: Optional[str] = None,
	filters: Any = None,
	search: Optional[str] = None,
) -> dict[str, Any]:
	if user or filters:
		payload = list_open_sales_orders_for_drill(
			user=user or frappe.session.user,
			company=company,
			filters=filters,
			limit=limit,
			offset=offset,
			search=search,
		)
		if not pending_delivery_only and status:
			orders = [o for o in payload["orders"] if o.get("status") == status]
			return {
				"rows": orders,
				"pagination": {
					"total": len(orders),
					"limit": int(limit),
					"offset": int(offset),
				},
			}
		return {
			"rows": payload["orders"],
			"pagination": {
				"total": payload["meta"].get("total_rows") or 0,
				"limit": int(limit),
				"offset": int(offset),
			},
			"meta": payload.get("meta"),
		}

	where, params = _open_so_where(company, territory, customer)
	extra_sql = ""
	if status:
		extra_sql += " AND so.status = %s"
		params.append(status)
	if pending_delivery_only:
		extra_sql += " AND so.per_delivered < 100"

	count_row = frappe.db.sql(
		f"""
		SELECT COUNT(*) AS total
		FROM `tabSales Order` so
		WHERE {where}
		{extra_sql}
		""",
		tuple(params),
		as_dict=True,
	)[0]
	total = int(count_row.total or 0)

	pending_expr = _pending_delivery_value_expr("so")
	list_params = [*params, int(limit), int(offset)]
	rows = frappe.db.sql(
		f"""
		SELECT
			so.name,
			so.customer,
			so.customer_name,
			COALESCE(so.territory, '') AS territory,
			so.transaction_date,
			so.delivery_date,
			so.status,
			COALESCE(so.per_delivered, 0) AS per_delivered,
			COALESCE(so.per_billed, 0) AS per_billed,
			COALESCE(so.base_grand_total, 0) AS grand_total,
			({pending_expr}) AS pending_delivery_value,
			(
				SELECT st.sales_person
				FROM `tabSales Team` st
				WHERE st.parent = so.name
				ORDER BY st.allocated_percentage DESC
				LIMIT 1
			) AS salesperson
		FROM `tabSales Order` so
		WHERE {where}
		{extra_sql}
		ORDER BY so.transaction_date DESC, so.name DESC
		LIMIT %s OFFSET %s
		""",
		tuple(list_params),
		as_dict=True,
	)

	return {
		"rows": [_format_open_order_row(row) for row in rows],
		"pagination": {"total": total, "limit": int(limit), "offset": int(offset)},
	}
