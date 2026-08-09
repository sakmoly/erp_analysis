"""Management exception rules — no target-miss exceptions."""

from __future__ import annotations

from typing import Any, Optional

import frappe

from erp_analysis.services.collection import get_overdue_customers, get_unallocated_payments
from erp_analysis.services.kpi.approvals_summary import get_pending_approvals_count
from erp_analysis.services.kpi.inventory_summary import get_inventory_summary_kpis
from erp_analysis.services.sales_orders import OPEN_SO_STATUSES


def get_overdue_ar_exceptions(
	company: Optional[str] = None,
	limit: int = 10,
) -> list[dict[str, Any]]:
	rows = get_overdue_customers(company=company, limit=limit)
	return [
		{
			"type": "overdue_ar",
			"key": row["customer"],
			"label": row["customer_name"],
			"territory": row["territory"],
			"amount": row["overdue"],
			"reference": row["customer"],
			"detail": {"total_outstanding": row["total_outstanding"], "oldest_due_date": row["oldest_due_date"]},
		}
		for row in rows
	]


def get_stale_so_exceptions(
	company: Optional[str] = None,
	stale_days: int = 90,
	limit: int = 10,
) -> list[dict[str, Any]]:
	company = company or frappe.defaults.get_user_default("Company")
	if not company:
		return []

	status_placeholders = ", ".join("%s" for _ in OPEN_SO_STATUSES)
	params: list[Any] = [*OPEN_SO_STATUSES, company, int(stale_days), int(limit)]

	rows = frappe.db.sql(
		f"""
		SELECT
			so.name,
			so.customer,
			COALESCE(so.customer_name, so.customer) AS customer_name,
			so.transaction_date,
			so.delivery_date,
			so.status,
			COALESCE(so.base_grand_total, 0) AS amount
		FROM `tabSales Order` so
		WHERE so.docstatus = 1
		  AND so.status NOT IN ({status_placeholders})
		  AND so.company = %s
		  AND (
			so.transaction_date < DATE_SUB(CURDATE(), INTERVAL %s DAY)
			OR (so.delivery_date < CURDATE() AND so.per_delivered < 100)
		  )
		ORDER BY so.transaction_date ASC
		LIMIT %s
		""",
		tuple(params),
		as_dict=True,
	)

	return [
		{
			"type": "stale_so",
			"key": row.name,
			"label": row.name,
			"amount": round(float(row.amount or 0), 2),
			"reference": row.customer,
			"detail": {
				"customer_name": row.customer_name,
				"transaction_date": str(row.transaction_date) if row.transaction_date else None,
				"delivery_date": str(row.delivery_date) if row.delivery_date else None,
				"status": row.status,
			},
		}
		for row in rows
	]


def get_low_stock_exceptions(
	company: Optional[str] = None,
	limit: int = 10,
) -> list[dict[str, Any]]:
	company = company or frappe.defaults.get_user_default("Company")
	if not company:
		return []

	rows = frappe.db.sql(
		"""
		SELECT
			b.item_code,
			COALESCE(i.item_name, b.item_code) AS item_name,
			b.warehouse,
			COALESCE(b.actual_qty, 0) AS actual_qty,
			COALESCE(ir.warehouse_reorder_level, 0) AS reorder_level
		FROM `tabBin` b
		INNER JOIN `tabWarehouse` w ON w.name = b.warehouse
		INNER JOIN `tabItem Reorder` ir
			ON ir.parent = b.item_code AND ir.warehouse = b.warehouse
		LEFT JOIN `tabItem` i ON i.name = b.item_code
		WHERE w.company = %s
		  AND ir.warehouse_reorder_level > 0
		  AND b.actual_qty <= ir.warehouse_reorder_level
		ORDER BY b.actual_qty ASC
		LIMIT %s
		""",
		(company, int(limit)),
		as_dict=True,
	)

	return [
		{
			"type": "low_stock",
			"key": f"{row.item_code}@{row.warehouse}",
			"label": row.item_name,
			"amount": round(float(row.actual_qty or 0), 2),
			"reference": row.item_code,
			"detail": {
				"warehouse": row.warehouse,
				"reorder_level": round(float(row.reorder_level or 0), 2),
			},
		}
		for row in rows
	]


def get_pending_approval_exceptions(
	company: Optional[str] = None,
	limit: int = 10,
) -> list[dict[str, Any]]:
	try:
		from erp_analysis.approvals import get_all_approvals

		result = get_all_approvals(company=company, limit=int(limit))
		message = result.get("message") if isinstance(result, dict) else {}
		approvals = message.get("approvals") or []
	except Exception:
		frappe.log_error(title="exceptions.pending_approval", message=frappe.get_traceback())
		return []

	items = []
	for row in approvals[: int(limit)]:
		items.append(
			{
				"type": "pending_approval",
				"key": row.get("name") or row.get("id"),
				"label": row.get("name") or row.get("id"),
				"amount": round(float(row.get("total_with_vat") or row.get("total_amount") or 0), 2),
				"reference": row.get("doctype"),
				"detail": {
					"doctype": row.get("doctype"),
					"customer_name": row.get("customer_name"),
					"status": row.get("status"),
					"posting_date": row.get("posting_date"),
				},
			}
		)
	return items


def get_management_exceptions_payload(
	company: Optional[str] = None,
	limit: int = 10,
	stale_days: int = 90,
) -> dict[str, Any]:
	overdue_ar = get_overdue_ar_exceptions(company=company, limit=limit)
	stale_so = get_stale_so_exceptions(company=company, stale_days=stale_days, limit=limit)
	low_stock = get_low_stock_exceptions(company=company, limit=limit)
	pending_approval = get_pending_approval_exceptions(company=company, limit=limit)
	inventory = get_inventory_summary_kpis(company=company)

	return {
		"summary": {
			"overdue_ar": len(overdue_ar),
			"stale_so": len(stale_so),
			"low_stock": int(inventory.get("low_stock_count") or len(low_stock)),
			"pending_approval": get_pending_approvals_count(company=company),
		},
		"overdue_ar": overdue_ar,
		"stale_so": stale_so,
		"low_stock": low_stock,
		"pending_approval": pending_approval,
		"unallocated_payments": [
			{
				"type": "unallocated_payment",
				"key": row["payment_entry"],
				"label": row["party"],
				"amount": row["unallocated_amount"],
				"reference": row["payment_entry"],
				"detail": row,
			}
			for row in get_unallocated_payments(company=company, min_unallocated=100, limit=limit)
		],
	}
