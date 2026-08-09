"""Approval analytics — counts by doctype, status, and aging."""

from __future__ import annotations

from typing import Any, Optional

import frappe
from frappe.utils import add_months, cint, getdate, nowdate


def _aging_bucket(posting_date) -> str:
	if not posting_date:
		return "unknown"
	days = (getdate(nowdate()) - getdate(posting_date)).days
	if days <= 7:
		return "0_7"
	if days <= 30:
		return "8_30"
	return "31_plus"


def _fetch_pending_sales_invoices(company: Optional[str], from_date: str, to_date: str) -> list[dict]:
	conds = [
		"si.docstatus = 0",
		"(si.status IS NULL OR si.status = 'Draft')",
		"si.posting_date BETWEEN %(from)s AND %(to)s",
	]
	vals: dict[str, Any] = {"from": from_date, "to": to_date}
	if company:
		conds.append("si.company = %(company)s")
		vals["company"] = company

	return frappe.db.sql(
		f"""
		SELECT
			'Sales Invoice' AS doctype,
			si.name,
			COALESCE(si.status, 'Draft') AS status,
			si.posting_date,
			COALESCE(si.base_grand_total, 0) AS amount
		FROM `tabSales Invoice` si
		WHERE {" AND ".join(conds)}
		""",
		vals,
		as_dict=True,
	)


def _fetch_pending_delivery_notes(
	company: Optional[str],
	from_date: str,
	to_date: str,
	workflow_states: Optional[list[str]] = None,
) -> list[dict]:
	conds = [
		"dn.docstatus = 0",
		"dn.posting_date BETWEEN %(from)s AND %(to)s",
	]
	vals: dict[str, Any] = {"from": from_date, "to": to_date}
	if company:
		conds.append("dn.company = %(company)s")
		vals["company"] = company
	if workflow_states:
		conds.append("dn.workflow_state IN %(states)s")
		vals["states"] = tuple(workflow_states)

	return frappe.db.sql(
		f"""
		SELECT
			'Delivery Note' AS doctype,
			dn.name,
			COALESCE(dn.workflow_state, dn.status, 'Draft') AS status,
			dn.posting_date,
			COALESCE(dn.base_grand_total, 0) AS amount
		FROM `tabDelivery Note` dn
		WHERE {" AND ".join(conds)}
		""",
		vals,
		as_dict=True,
	)


def get_approval_summary_payload(
	company: Optional[str] = None,
	from_date: Optional[str] = None,
	to_date: Optional[str] = None,
) -> dict[str, Any]:
	company = company or frappe.defaults.get_user_default("Company")
	from_date = str(getdate(from_date or add_months(nowdate(), -2)))
	to_date = str(getdate(to_date or nowdate()))

	rows = _fetch_pending_sales_invoices(company, from_date, to_date)
	rows.extend(
		_fetch_pending_delivery_notes(
			company,
			from_date,
			to_date,
			workflow_states=["Approved By Finance Coordinator"],
		)
	)

	by_doctype: dict[str, int] = {}
	by_status: dict[str, int] = {}
	aging = {"0_7": 0, "8_30": 0, "31_plus": 0, "unknown": 0}
	total_amount = 0.0

	for row in rows:
		doctype = row.doctype or "Unknown"
		status = row.status or "Draft"
		by_doctype[doctype] = by_doctype.get(doctype, 0) + 1
		status_key = f"{doctype}:{status}"
		by_status[status_key] = by_status.get(status_key, 0) + 1
		bucket = _aging_bucket(row.posting_date)
		aging[bucket] = aging.get(bucket, 0) + 1
		total_amount += float(row.amount or 0)

	return {
		"period": {"from_date": from_date, "to_date": to_date},
		"total_pending": len(rows),
		"total_amount": round(total_amount, 2),
		"by_doctype": [
			{"doctype": key, "count": count}
			for key, count in sorted(by_doctype.items(), key=lambda x: (-x[1], x[0]))
		],
		"by_status": [
			{"status": key, "count": count}
			for key, count in sorted(by_status.items(), key=lambda x: (-x[1], x[0]))
		],
		"aging": aging,
	}
