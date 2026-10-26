"""Accounts payable queries for dashboard and executive KPIs."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Optional

import frappe
from frappe.utils import getdate, nowdate


def _company_sql(company: Optional[str], alias: str = "pi") -> tuple[str, list[Any]]:
	if not company:
		return "", []
	return f" AND {alias}.company = %s", [company]


def _open_pi_where(company: Optional[str] = None, alias: str = "pi") -> tuple[str, list[Any]]:
	company_sql, company_params = _company_sql(company, alias)
	where = f"""
		{alias}.docstatus = 1
		AND {alias}.outstanding_amount > 0
		{company_sql}
	"""
	return where, company_params


def get_payables_summary(company: Optional[str] = None) -> dict[str, Any]:
	"""Compact KPI block for executive dashboard."""
	company = company or frappe.defaults.get_user_default("Company")
	where, params = _open_pi_where(company)

	row = frappe.db.sql(
		f"""
		SELECT
			COALESCE(SUM(pi.outstanding_amount), 0) AS total,
			COALESCE(SUM(
				CASE WHEN pi.due_date < CURDATE() THEN pi.outstanding_amount ELSE 0 END
			), 0) AS overdue
		FROM `tabPurchase Invoice` pi
		WHERE {where}
		""",
		tuple(params),
		as_dict=True,
	)[0]

	total = float(row.total or 0)
	overdue = float(row.overdue or 0)
	overdue_pct = round(overdue / total * 100, 2) if total > 0 else 0.0

	return {
		"total": round(total, 2),
		"overdue": round(overdue, 2),
		"overdue_pct": overdue_pct,
	}


def get_payables_aging_buckets(company: Optional[str] = None) -> dict[str, float]:
	where, params = _open_pi_where(company)

	row = frappe.db.sql(
		f"""
		SELECT
			COALESCE(SUM(
				CASE WHEN pi.due_date >= CURDATE() OR pi.due_date IS NULL THEN pi.outstanding_amount ELSE 0 END
			), 0) AS current_bucket,
			COALESCE(SUM(
				CASE WHEN pi.due_date < CURDATE()
				  AND DATEDIFF(CURDATE(), pi.due_date) BETWEEN 1 AND 30
				THEN pi.outstanding_amount ELSE 0 END
			), 0) AS d30,
			COALESCE(SUM(
				CASE WHEN pi.due_date < CURDATE()
				  AND DATEDIFF(CURDATE(), pi.due_date) BETWEEN 31 AND 60
				THEN pi.outstanding_amount ELSE 0 END
			), 0) AS d60,
			COALESCE(SUM(
				CASE WHEN pi.due_date < CURDATE()
				  AND DATEDIFF(CURDATE(), pi.due_date) BETWEEN 61 AND 90
				THEN pi.outstanding_amount ELSE 0 END
			), 0) AS d90,
			COALESCE(SUM(
				CASE WHEN pi.due_date < CURDATE()
				  AND DATEDIFF(CURDATE(), pi.due_date) > 90
				THEN pi.outstanding_amount ELSE 0 END
			), 0) AS d120p
		FROM `tabPurchase Invoice` pi
		WHERE {where}
		""",
		tuple(params),
		as_dict=True,
	)[0]

	return {
		"current": round(float(row.current_bucket or 0), 2),
		"d30": round(float(row.d30 or 0), 2),
		"d60": round(float(row.d60 or 0), 2),
		"d90": round(float(row.d90 or 0), 2),
		"d120p": round(float(row.d120p or 0), 2),
	}


def get_open_payables_invoices(
	company: Optional[str] = None,
	*,
	supplier: Optional[str] = None,
	limit: int = 500,
) -> list[dict[str, Any]]:
	"""Open Purchase Invoice lines for payables drill (supplier detail on mobile)."""
	where, params = _open_pi_where(company)
	supplier_sql = ""
	if supplier and str(supplier).strip():
		supplier_sql = " AND pi.supplier = %s"
		params = [*params, str(supplier).strip()]

	rows = frappe.db.sql(
		f"""
		SELECT
			pi.name AS invoice,
			pi.name AS purchase_invoice,
			pi.supplier,
			COALESCE(pi.supplier_name, pi.supplier) AS supplier_name,
			pi.posting_date,
			pi.due_date,
			COALESCE(pi.outstanding_amount, 0) AS outstanding,
			COALESCE(pi.outstanding_amount, 0) AS outstanding_amount,
			COALESCE(pi.grand_total, 0) AS grand_total,
			COALESCE(pi.bill_no, '') AS bill_no,
			CASE
				WHEN pi.due_date IS NULL THEN 0
				WHEN pi.due_date >= CURDATE() THEN 0
				ELSE DATEDIFF(CURDATE(), pi.due_date)
			END AS days_overdue
		FROM `tabPurchase Invoice` pi
		WHERE {where}
		{supplier_sql}
		ORDER BY pi.due_date ASC, pi.outstanding_amount DESC
		LIMIT %s
		""",
		tuple([*params, int(limit)]),
		as_dict=True,
	)

	out: list[dict[str, Any]] = []
	for row in rows:
		out.append(
			{
				"invoice": row.invoice,
				"purchase_invoice": row.purchase_invoice,
				"supplier": row.supplier,
				"supplier_name": row.supplier_name,
				"posting_date": str(row.posting_date) if row.posting_date else None,
				"due_date": str(row.due_date) if row.due_date else None,
				"outstanding": round(float(row.outstanding or 0), 2),
				"outstanding_amount": round(float(row.outstanding_amount or 0), 2),
				"grand_total": round(float(row.grand_total or 0), 2),
				"bill_no": row.bill_no or None,
				"days_overdue": int(row.days_overdue or 0),
			}
		)
	return out


def get_payables_by_supplier(
	company: Optional[str] = None,
	limit: int = 20,
) -> list[dict[str, Any]]:
	where, params = _open_pi_where(company)

	rows = frappe.db.sql(
		f"""
		SELECT
			pi.supplier,
			COALESCE(pi.supplier_name, pi.supplier) AS supplier_name,
			COALESCE(SUM(pi.outstanding_amount), 0) AS outstanding,
			COALESCE(SUM(
				CASE WHEN pi.due_date < CURDATE() THEN pi.outstanding_amount ELSE 0 END
			), 0) AS overdue,
			COUNT(*) AS invoice_count
		FROM `tabPurchase Invoice` pi
		WHERE {where}
		GROUP BY pi.supplier, pi.supplier_name
		ORDER BY outstanding DESC
		LIMIT %s
		""",
		tuple([*params, int(limit)]),
		as_dict=True,
	)

	return [
		{
			"supplier": row.supplier,
			"supplier_name": row.supplier_name,
			"outstanding": round(float(row.outstanding or 0), 2),
			"overdue": round(float(row.overdue or 0), 2),
			"invoice_count": int(row.invoice_count or 0),
		}
		for row in rows
	]


def get_payables_dashboard_payload(
	company: Optional[str] = None,
	limit: int = 20,
	*,
	supplier: Optional[str] = None,
	include_invoices: bool = True,
	invoice_limit: int = 500,
) -> dict[str, Any]:
	summary = get_payables_summary(company=company)
	where, params = _open_pi_where(company)

	extra = frappe.db.sql(
		f"""
		SELECT COUNT(*) AS invoice_count
		FROM `tabPurchase Invoice` pi
		WHERE {where}
		""",
		tuple(params),
		as_dict=True,
	)[0]

	invoices: list[dict[str, Any]] = []
	if include_invoices:
		invoices = get_open_payables_invoices(
			company,
			supplier=supplier,
			limit=invoice_limit,
		)

	payload: dict[str, Any] = {
		"kpis": {
			**summary,
			"invoice_count": int(extra.invoice_count or 0),
		},
		"aging_buckets": get_payables_aging_buckets(company=company),
		"by_supplier": get_payables_by_supplier(company=company, limit=limit),
		"invoices": invoices,
		"open_invoices": invoices,
	}
	if supplier and str(supplier).strip():
		payload["supplier"] = str(supplier).strip()
		matched = [row for row in payload["by_supplier"] if row.get("supplier") == payload["supplier"]]
		if matched:
			payload["supplier_summary"] = matched[0]
		elif invoices:
			payload["supplier_summary"] = {
				"supplier": payload["supplier"],
				"supplier_name": invoices[0].get("supplier_name") or payload["supplier"],
				"outstanding": round(sum(float(i.get("outstanding") or 0) for i in invoices), 2),
				"overdue": round(
					sum(
						float(i.get("outstanding") or 0)
						for i in invoices
						if int(i.get("days_overdue") or 0) > 0
					),
					2,
				),
				"invoice_count": len(invoices),
			}
	return payload


def get_payment_planning_payload(
	company: Optional[str] = None,
	days_ahead: int = 30,
	limit: int = 20,
) -> dict[str, Any]:
	"""Upcoming due payables and overdue supplier attention list."""
	company = company or frappe.defaults.get_user_default("Company")
	where, params = _open_pi_where(company)
	today = getdate(nowdate())
	horizon = today + timedelta(days=int(days_ahead))

	upcoming = frappe.db.sql(
		f"""
		SELECT
			pi.name AS invoice,
			pi.supplier,
			COALESCE(pi.supplier_name, pi.supplier) AS supplier_name,
			pi.due_date,
			COALESCE(pi.outstanding_amount, 0) AS outstanding
		FROM `tabPurchase Invoice` pi
		WHERE {where}
		  AND pi.due_date IS NOT NULL
		  AND pi.due_date >= %s
		  AND pi.due_date <= %s
		ORDER BY pi.due_date ASC, pi.outstanding_amount DESC
		LIMIT %s
		""",
		tuple([*params, today, horizon, int(limit)]),
		as_dict=True,
	)

	overdue_suppliers = frappe.db.sql(
		f"""
		SELECT
			pi.supplier,
			COALESCE(pi.supplier_name, pi.supplier) AS supplier_name,
			COALESCE(SUM(pi.outstanding_amount), 0) AS overdue,
			COUNT(*) AS invoice_count,
			MIN(pi.due_date) AS oldest_due_date
		FROM `tabPurchase Invoice` pi
		WHERE {where}
		  AND pi.due_date < CURDATE()
		GROUP BY pi.supplier, pi.supplier_name
		ORDER BY overdue DESC
		LIMIT %s
		""",
		tuple([*params, int(limit)]),
		as_dict=True,
	)

	return {
		"days_ahead": int(days_ahead),
		"due_soon": [
			{
				"invoice": row.invoice,
				"supplier": row.supplier,
				"supplier_name": row.supplier_name,
				"due_date": str(row.due_date),
				"outstanding": round(float(row.outstanding or 0), 2),
			}
			for row in upcoming
		],
		"overdue_suppliers": [
			{
				"supplier": row.supplier,
				"supplier_name": row.supplier_name,
				"overdue": round(float(row.overdue or 0), 2),
				"invoice_count": int(row.invoice_count or 0),
				"oldest_due_date": str(row.oldest_due_date) if row.oldest_due_date else None,
			}
			for row in overdue_suppliers
		],
	}
