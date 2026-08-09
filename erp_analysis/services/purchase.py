"""Open Purchase Order queries for purchase dashboard and executive KPIs."""

from __future__ import annotations

from typing import Any, Optional

import frappe

OPEN_PO_STATUSES = ("Closed", "Completed", "Cancelled", "Draft")


def _company_sql(company: Optional[str], alias: str = "po") -> tuple[str, list[Any]]:
	if not company:
		return "", []
	return f" AND {alias}.company = %s", [company]


def _open_po_where(
	company: Optional[str] = None,
	alias: str = "po",
) -> tuple[str, list[Any]]:
	company_sql, company_params = _company_sql(company, alias)
	where = f"""
		{alias}.docstatus = 1
		AND {alias}.status NOT IN ({", ".join("%s" for _ in OPEN_PO_STATUSES)})
		{company_sql}
	"""
	params = [*OPEN_PO_STATUSES, *company_params]
	return where, params


def get_purchase_summary(company: Optional[str] = None) -> dict[str, Any]:
	"""Compact KPI block for executive dashboard."""
	company = company or frappe.defaults.get_user_default("Company")
	where, params = _open_po_where(company)

	row = frappe.db.sql(
		f"""
		SELECT
			COUNT(*) AS open_count,
			COALESCE(SUM(po.base_grand_total), 0) AS open_value,
			COALESCE(SUM(CASE WHEN po.per_received < 100 THEN 1 ELSE 0 END), 0) AS pending_receipt_count,
			COALESCE(SUM(
				CASE WHEN po.per_received < 100 THEN po.base_grand_total ELSE 0 END
			), 0) AS pending_receipt_value
		FROM `tabPurchase Order` po
		WHERE {where}
		""",
		tuple(params),
		as_dict=True,
	)[0]

	return {
		"open_count": int(row.open_count or 0),
		"open_value": round(float(row.open_value or 0), 2),
		"pending_receipt_count": int(row.pending_receipt_count or 0),
		"pending_receipt_value": round(float(row.pending_receipt_value or 0), 2),
	}


def get_purchase_by_status(
	company: Optional[str] = None,
	limit: int = 10,
) -> list[dict[str, Any]]:
	where, params = _open_po_where(company)

	rows = frappe.db.sql(
		f"""
		SELECT
			po.status,
			COUNT(*) AS order_count,
			COALESCE(SUM(po.base_grand_total), 0) AS order_value
		FROM `tabPurchase Order` po
		WHERE {where}
		GROUP BY po.status
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


def get_purchase_by_supplier(
	company: Optional[str] = None,
	limit: int = 10,
) -> list[dict[str, Any]]:
	where, params = _open_po_where(company)

	rows = frappe.db.sql(
		f"""
		SELECT
			po.supplier,
			COALESCE(po.supplier_name, po.supplier) AS supplier_name,
			COUNT(*) AS order_count,
			COALESCE(SUM(po.base_grand_total), 0) AS order_value,
			COALESCE(SUM(
				CASE WHEN po.per_received < 100 THEN po.base_grand_total ELSE 0 END
			), 0) AS pending_receipt_value
		FROM `tabPurchase Order` po
		WHERE {where}
		GROUP BY po.supplier, po.supplier_name
		ORDER BY order_value DESC
		LIMIT %s
		""",
		tuple([*params, int(limit)]),
		as_dict=True,
	)

	return [
		{
			"supplier": row.supplier,
			"supplier_name": row.supplier_name,
			"order_count": int(row.order_count or 0),
			"order_value": round(float(row.order_value or 0), 2),
			"pending_receipt_value": round(float(row.pending_receipt_value or 0), 2),
		}
		for row in rows
	]


def get_purchase_dashboard_payload(
	company: Optional[str] = None,
	limit: int = 10,
) -> dict[str, Any]:
	summary = get_purchase_summary(company=company)
	where, params = _open_po_where(company)

	extra = frappe.db.sql(
		f"""
		SELECT
			COALESCE(SUM(CASE WHEN po.per_billed < 100 THEN 1 ELSE 0 END), 0) AS to_bill_count,
			COALESCE(SUM(
				CASE WHEN po.schedule_date < CURDATE() AND po.per_received < 100 THEN 1 ELSE 0 END
			), 0) AS overdue_receipt_count
		FROM `tabPurchase Order` po
		WHERE {where}
		""",
		tuple(params),
		as_dict=True,
	)[0]

	kpis = {
		**summary,
		"to_bill_count": int(extra.to_bill_count or 0),
		"overdue_receipt_count": int(extra.overdue_receipt_count or 0),
	}

	return {
		"kpis": kpis,
		"by_status": get_purchase_by_status(company=company, limit=limit),
		"by_supplier": get_purchase_by_supplier(company=company, limit=limit),
	}


def get_open_purchase_orders(
	company: Optional[str] = None,
	status: Optional[str] = None,
	pending_receipt_only: bool = False,
	limit: int = 50,
	offset: int = 0,
) -> dict[str, Any]:
	where, params = _open_po_where(company)
	extra_sql = ""
	if status:
		extra_sql += " AND po.status = %s"
		params.append(status)
	if pending_receipt_only:
		extra_sql += " AND po.per_received < 100"

	count_row = frappe.db.sql(
		f"""
		SELECT COUNT(*) AS total
		FROM `tabPurchase Order` po
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
			po.name,
			po.supplier,
			po.supplier_name,
			po.transaction_date,
			po.schedule_date,
			po.status,
			COALESCE(po.per_received, 0) AS per_received,
			COALESCE(po.per_billed, 0) AS per_billed,
			COALESCE(po.base_grand_total, 0) AS amount
		FROM `tabPurchase Order` po
		WHERE {where}
		{extra_sql}
		ORDER BY po.transaction_date DESC, po.name DESC
		LIMIT %s OFFSET %s
		""",
		tuple(list_params),
		as_dict=True,
	)

	return {
		"rows": [
			{
				"name": row.name,
				"supplier": row.supplier,
				"supplier_name": row.supplier_name or row.supplier,
				"transaction_date": str(row.transaction_date) if row.transaction_date else None,
				"schedule_date": str(row.schedule_date) if row.schedule_date else None,
				"status": row.status,
				"per_received": round(float(row.per_received or 0), 2),
				"per_billed": round(float(row.per_billed or 0), 2),
				"amount": round(float(row.amount or 0), 2),
			}
			for row in rows
		],
		"pagination": {"total": total, "limit": int(limit), "offset": int(offset)},
	}
