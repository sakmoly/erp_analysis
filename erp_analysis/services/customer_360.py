"""Customer 360 composition — mobile Phase 3C contract."""

from __future__ import annotations

from calendar import month_abbr
from datetime import date
from typing import Any, Optional

import frappe
from frappe.utils import add_days, add_months, get_first_day, get_last_day, getdate, nowdate

from erp_analysis.services.sales_orders import get_open_sales_orders
from erp_analysis.utils.rpc import resolve_customer_id
from erp_analysis.utils.schema import customer_credit_limit, existing_fields, safe_get_value

CHART_MONTHS = 6

# Core Customer fields — selected only if present on this site's meta.
_CUSTOMER_PROFILE_FIELDS = (
	"name",
	"customer_name",
	"territory",
	"customer_group",
	"customer_type",
	"mobile_no",
	"email_id",
	"tax_id",
	"payment_terms",
)

_CUSTOMER_SHELL_FIELDS = ("name", "customer_name", "territory")


def get_customer_profile(
	customer: str,
	company: Optional[str] = None,
) -> dict[str, Any]:
	"""Full profile for other endpoints (includes credit — schema-safe)."""
	if not frappe.db.exists("Customer", customer):
		return {
			"name": customer,
			"customer_name": customer,
			"territory": "",
			"customer_group": "",
			"customer_type": "",
			"mobile_no": "",
			"email_id": "",
			"tax_id": "",
			"payment_terms": "",
			"credit_limit": 0.0,
		}

	row = safe_get_value("Customer", customer, _CUSTOMER_PROFILE_FIELDS) or {}
	company = company or frappe.defaults.get_user_default("Company")
	return {
		"name": row.get("name") or customer,
		"customer_name": row.get("customer_name") or customer,
		"territory": row.get("territory") or "",
		"customer_group": row.get("customer_group") or "",
		"customer_type": row.get("customer_type") or "",
		"mobile_no": row.get("mobile_no") or "",
		"email_id": row.get("email_id") or "",
		"tax_id": row.get("tax_id") or "",
		"payment_terms": row.get("payment_terms") or "",
		# Never SELECT Customer.credit_limit — use child table / optional column helper.
		"credit_limit": customer_credit_limit(customer, company),
	}


def get_customer_object(customer: str) -> dict[str, Any]:
	"""Mobile shell — no DSO / credit fields; minimal safe SELECT only."""
	if not frappe.db.exists("Customer", customer):
		return {"id": customer, "customer_name": customer, "territory": ""}

	fields = existing_fields("Customer", _CUSTOMER_SHELL_FIELDS) or ["name"]
	row = frappe.db.get_value("Customer", customer, fields, as_dict=True) or {}
	return {
		"id": row.get("name") or customer,
		"customer_name": row.get("customer_name") or customer,
		"territory": row.get("territory") or "",
	}


def _safe_customer_shell(customer_id: str) -> dict[str, Any]:
	"""Never raise from empty/error payload path."""
	try:
		return get_customer_object(customer_id)
	except Exception:
		frappe.log_error(
			title="customer_360._safe_customer_shell",
			message=frappe.get_traceback(),
		)
		return {"id": customer_id, "customer_name": customer_id, "territory": ""}


def get_customer_receivables_block(
	company: Optional[str] = None,
	customer: Optional[str] = None,
	chart_months: int = CHART_MONTHS,
) -> dict[str, Any]:
	"""Receivables KPIs for Customer 360 (outstanding / overdue / current + averages)."""
	company = company or frappe.defaults.get_user_default("Company")
	empty = {
		"outstanding": 0.0,
		"overdue": 0.0,
		"current": 0.0,
		"avg_monthly_sales": 0.0,
		"monthly_receivable": 0.0,
		"oldest_invoice": None,
	}
	if not company or not customer:
		return empty

	row = frappe.db.sql(
		"""
		SELECT
			COALESCE(SUM(si.outstanding_amount), 0) AS outstanding,
			COALESCE(SUM(
				CASE WHEN si.due_date < CURDATE() THEN si.outstanding_amount ELSE 0 END
			), 0) AS overdue,
			MIN(CASE WHEN si.outstanding_amount > 0 THEN si.posting_date END) AS oldest_invoice
		FROM `tabSales Invoice` si
		WHERE si.docstatus = 1
		  AND si.outstanding_amount > 0
		  AND si.company = %s
		  AND si.customer = %s
		""",
		(company, customer),
		as_dict=True,
	)[0]

	outstanding = round(float(row.outstanding or 0), 2)
	overdue = round(float(row.overdue or 0), 2)
	current = round(max(outstanding - overdue, 0.0), 2)

	charts = get_customer_charts(company=company, customer=customer, months=chart_months)
	sales_vals = charts.get("sales") or []
	receivable_vals = charts.get("receivables") or []

	avg_monthly_sales = round(sum(sales_vals) / len(sales_vals), 2) if sales_vals else 0.0
	monthly_receivable = round(sum(receivable_vals) / len(receivable_vals), 2) if receivable_vals else 0.0

	oldest = row.oldest_invoice
	return {
		"outstanding": outstanding,
		"overdue": overdue,
		"current": current,
		"avg_monthly_sales": avg_monthly_sales,
		"monthly_receivable": monthly_receivable,
		"oldest_invoice": str(oldest) if oldest else None,
	}


def _month_periods(end_date: date, count: int) -> list[tuple[date, date, str]]:
	"""Last N calendar months ending at end_date's month (oldest first)."""
	periods: list[tuple[date, date, str]] = []
	anchor = getdate(get_first_day(end_date))
	for i in range(count - 1, -1, -1):
		month_start = getdate(add_months(anchor, -i))
		month_end = getdate(get_last_day(month_start))
		label = month_abbr[month_start.month]
		periods.append((month_start, month_end, label))
	return periods


def get_customer_charts(
	company: Optional[str] = None,
	customer: Optional[str] = None,
	months: int = CHART_MONTHS,
) -> dict[str, Any]:
	"""Monthly sales, collection, and month-end receivable series for charts."""
	company = company or frappe.defaults.get_user_default("Company")
	if not company or not customer:
		return {"months": [], "sales": [], "collection": [], "receivables": []}

	end = getdate(nowdate())
	periods = _month_periods(end, months)
	if not periods:
		return {"months": [], "sales": [], "collection": [], "receivables": []}

	range_start = periods[0][0]
	range_end = periods[-1][1]

	sales_rows = frappe.db.sql(
		"""
		SELECT
			YEAR(si.posting_date) AS y,
			MONTH(si.posting_date) AS m,
			COALESCE(SUM(si.base_grand_total), 0) AS sales
		FROM `tabSales Invoice` si
		WHERE si.docstatus = 1
		  AND si.company = %s
		  AND si.customer = %s
		  AND si.posting_date BETWEEN %s AND %s
		GROUP BY YEAR(si.posting_date), MONTH(si.posting_date)
		""",
		(company, customer, range_start, range_end),
		as_dict=True,
	)
	sales_map = {(int(r.y), int(r.m)): float(r.sales or 0) for r in sales_rows}

	collection_rows = frappe.db.sql(
		"""
		SELECT
			YEAR(pe.posting_date) AS y,
			MONTH(pe.posting_date) AS m,
			COALESCE(SUM(per.allocated_amount), 0) AS collected
		FROM `tabPayment Entry` pe
		INNER JOIN `tabPayment Entry Reference` per ON per.parent = pe.name
		WHERE pe.docstatus = 1
		  AND pe.payment_type = 'Receive'
		  AND pe.party_type = 'Customer'
		  AND pe.party = %s
		  AND pe.company = %s
		  AND pe.posting_date BETWEEN %s AND %s
		GROUP BY YEAR(pe.posting_date), MONTH(pe.posting_date)
		""",
		(customer, company, range_start, range_end),
		as_dict=True,
	)
	collection_map = {(int(r.y), int(r.m)): float(r.collected or 0) for r in collection_rows}

	months_labels: list[str] = []
	sales: list[float] = []
	collection: list[float] = []
	receivables: list[float] = []

	for month_start, month_end, label in periods:
		key = (month_start.year, month_start.month)
		months_labels.append(label)
		sales.append(round(sales_map.get(key, 0.0), 2))
		collection.append(round(collection_map.get(key, 0.0), 2))
		receivables.append(
			round(_receivable_as_of(company, customer, month_end), 2)
		)

	return {
		"months": months_labels,
		"sales": sales,
		"collection": collection,
		"receivables": receivables,
	}


def _receivable_as_of(company: str, customer: str, as_of: date) -> float:
	"""Customer AR balance at month-end from invoices minus payments allocated by that date."""
	row = frappe.db.sql(
		"""
		SELECT COALESCE(SUM(
			GREATEST(
				COALESCE(si.base_grand_total, 0) - COALESCE(paid.paid_amount, 0),
				0
			)
		), 0) AS balance
		FROM `tabSales Invoice` si
		LEFT JOIN (
			SELECT
				per.reference_name AS invoice_name,
				SUM(per.allocated_amount) AS paid_amount
			FROM `tabPayment Entry Reference` per
			INNER JOIN `tabPayment Entry` pe ON pe.name = per.parent
			WHERE pe.docstatus = 1
			  AND pe.posting_date <= %s
			GROUP BY per.reference_name
		) paid ON paid.invoice_name = si.name
		WHERE si.docstatus = 1
		  AND si.company = %s
		  AND si.customer = %s
		  AND si.posting_date <= %s
		""",
		(as_of, company, customer, as_of),
		as_dict=True,
	)[0]
	return float(row.balance or 0)


def get_recent_invoices(
	company: Optional[str] = None,
	customer: Optional[str] = None,
	limit: int = 10,
) -> list[dict[str, Any]]:
	if not company or not customer:
		return []

	rows = frappe.db.sql(
		"""
		SELECT
			si.name,
			si.posting_date,
			si.due_date,
			si.status,
			COALESCE(si.base_grand_total, 0) AS amount,
			COALESCE(si.outstanding_amount, 0) AS outstanding
		FROM `tabSales Invoice` si
		WHERE si.docstatus = 1
		  AND si.company = %s
		  AND si.customer = %s
		ORDER BY si.posting_date DESC, si.name DESC
		LIMIT %s
		""",
		(company, customer, int(limit)),
		as_dict=True,
	)

	return [
		{
			"name": row.name,
			"posting_date": str(row.posting_date) if row.posting_date else None,
			"due_date": str(row.due_date) if row.due_date else None,
			"status": row.status,
			"amount": round(float(row.amount or 0), 2),
			"outstanding": round(float(row.outstanding or 0), 2),
		}
		for row in rows
	]


def get_statement_link(
	company: Optional[str],
	customer: str,
	from_date: Optional[str] = None,
	to_date: Optional[str] = None,
) -> dict[str, Any]:
	to_date = to_date or str(nowdate())
	if not from_date:
		from_date = str(getdate(add_days(to_date, -90)))

	return {
		"method": "erp_analysis.receivables.get_customer_statement",
		"params": {
			"company": company,
			"customer": customer,
			"from_date": from_date,
			"to_date": to_date,
		},
		"pdf_method": "erp_analysis.customer_notifications.send_statement_pdf",
	}


def get_customer_360_payload(
	company: Optional[str] = None,
	customer: Optional[str] = None,
	from_date: Optional[str] = None,
	to_date: Optional[str] = None,
	invoice_limit: int = 10,
	open_so_limit: int = 10,
) -> dict[str, Any]:
	company = company or frappe.defaults.get_user_default("Company")
	customer_id = resolve_customer_id(customer)
	if not customer_id:
		frappe.throw("Customer is required", frappe.MandatoryError)

	receivables = get_customer_receivables_block(company=company, customer=customer_id)
	charts = get_customer_charts(company=company, customer=customer_id)
	recent_invoices = get_recent_invoices(company=company, customer=customer_id, limit=invoice_limit)
	open_orders = get_open_sales_orders(
		company=company,
		customer=customer_id,
		limit=open_so_limit,
		offset=0,
	)

	return {
		"customer": get_customer_object(customer_id),
		"company": company,
		"receivables": receivables,
		"charts": charts,
		"recent_invoices": recent_invoices,
		"open_sales_orders": open_orders,
		"statement": get_statement_link(
			company=company,
			customer=customer_id,
			from_date=from_date,
			to_date=to_date,
		),
	}


def empty_customer_360_payload(
	company: Optional[str],
	customer_id: str,
	from_date: Optional[str] = None,
	to_date: Optional[str] = None,
	open_so_limit: int = 10,
) -> dict[str, Any]:
	"""Degraded payload — must not re-hit broken SELECT lists."""
	statement = {
		"company": company,
		"customer": customer_id,
		"from_date": from_date,
		"to_date": to_date,
		"pdf_method": "erp_analysis.customer_notifications.send_statement_pdf",
	}
	try:
		statement = get_statement_link(
			company=company,
			customer=customer_id,
			from_date=from_date,
			to_date=to_date,
		)
	except Exception:
		frappe.log_error(
			title="customer_360.empty_statement",
			message=frappe.get_traceback(),
		)

	return {
		"customer": _safe_customer_shell(customer_id),
		"company": company,
		"receivables": {
			"outstanding": 0.0,
			"overdue": 0.0,
			"current": 0.0,
			"avg_monthly_sales": 0.0,
			"monthly_receivable": 0.0,
			"oldest_invoice": None,
		},
		"charts": {"months": [], "sales": [], "collection": [], "receivables": []},
		"recent_invoices": [],
		"open_sales_orders": {"rows": [], "pagination": {"total": 0, "limit": open_so_limit, "offset": 0}},
		"statement": statement,
	}


# Backward-compatible helper name used by receivables drill-downs.
def get_customer_receivables_snapshot(
	company: Optional[str] = None,
	customer: Optional[str] = None,
) -> dict[str, Any]:
	block = get_customer_receivables_block(company=company, customer=customer)
	total = block["outstanding"]
	overdue = block["overdue"]
	return {
		"total_outstanding": total,
		"overdue": overdue,
		"overdue_pct": round(overdue / total * 100, 2) if total > 0 else 0.0,
		"aging_buckets": {
			"current": block["current"],
			"d30": 0,
			"d60": 0,
			"d90": 0,
			"d120p": overdue,
		},
	}
