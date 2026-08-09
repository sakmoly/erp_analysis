"""Open Sales Order queries for order book dashboard and executive KPIs."""

from __future__ import annotations

from typing import Any, Optional

import frappe

OPEN_SO_STATUSES = ("Closed", "Completed", "Cancelled", "Draft")


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


def _open_so_where(
	company: Optional[str] = None,
	territory: Optional[str] = None,
	customer: Optional[str] = None,
	alias: str = "so",
	territories: Optional[list[str]] = None,
) -> tuple[str, list[Any]]:
	from erp_analysis.permissions.access_profile import resolve_territory_scope

	if territories is None:
		territories = resolve_territory_scope(
			requested=territory, company=company, purpose="view", module="sales"
		)

	company_sql, company_params = _company_sql(company, alias)
	territory_sql, territory_params = _territory_sql(
		territory=None, territories=territories, alias=alias
	)
	customer_sql, customer_params = _customer_sql(customer, alias)
	where = f"""
		{alias}.docstatus = 1
		AND {alias}.status NOT IN ({", ".join("%s" for _ in OPEN_SO_STATUSES)})
		{company_sql}
		{territory_sql}
		{customer_sql}
	"""
	params = [*OPEN_SO_STATUSES, *company_params, *territory_params, *customer_params]
	return where, params


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


def get_open_sales_orders(
	company: Optional[str] = None,
	territory: Optional[str] = None,
	customer: Optional[str] = None,
	status: Optional[str] = None,
	pending_delivery_only: bool = False,
	limit: int = 50,
	offset: int = 0,
) -> dict[str, Any]:
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
			COALESCE(so.base_grand_total, 0) AS amount
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
		"rows": [
			{
				"name": row.name,
				"customer": row.customer,
				"customer_name": row.customer_name or row.customer,
				"territory": row.territory,
				"transaction_date": str(row.transaction_date) if row.transaction_date else None,
				"delivery_date": str(row.delivery_date) if row.delivery_date else None,
				"status": row.status,
				"per_delivered": round(float(row.per_delivered or 0), 2),
				"per_billed": round(float(row.per_billed or 0), 2),
				"amount": round(float(row.amount or 0), 2),
			}
			for row in rows
		],
		"pagination": {"total": total, "limit": int(limit), "offset": int(offset)},
	}
