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


def _sdb_customer_columns() -> set[str]:
	if not frappe.db.table_exists("SalesDashBoard"):
		return set()
	try:
		return {c["Field"] for c in frappe.db.sql("SHOW COLUMNS FROM `tabSalesDashBoard`", as_dict=True)}
	except Exception:
		return set()


def _sdb_customer_scope_sql(
	customer: str,
	invoice_col: str = "Invoice_No",
) -> tuple[str, list[Any]]:
	"""SDB.Customer stores customer_name (label); scope by Sales Invoice link id."""
	return (
		f" AND `{invoice_col}` IN ("
		f"SELECT name FROM `tabSales Invoice` WHERE customer = %s AND docstatus = 1)",
		[customer],
	)


def _customer_net_and_cogs(
	company: str,
	customer: str,
	from_date: date,
	to_date: date,
) -> tuple[float, float]:
	"""Net sales + COGS for one customer (SalesDashBoard / Printechs GP, else submitted SI)."""
	cols = _sdb_customer_columns()
	if cols and "Invoice_No" in cols:
		company_sql = ""
		params: list[Any] = [from_date, to_date]
		if company and "Company" in cols:
			company_sql = " AND `Company` = %s"
			params.append(company)
		elif company and "company" in cols:
			company_sql = " AND company = %s"
			params.append(company)
		cust_sql, cust_params = _sdb_customer_scope_sql(customer)
		params.extend(cust_params)

		sales_col = "Net_Amount" if "Net_Amount" in cols else "net_amount"
		cogs_col = "COGS" if "COGS" in cols else "cogs"
		date_col = "Invoice_Date" if "Invoice_Date" in cols else "invoice_date"
		if sales_col in cols and date_col in cols:
			row = frappe.db.sql(
				f"""
				SELECT
					COALESCE(SUM(`{sales_col}`), 0) AS net_sales,
					COALESCE(SUM(`{cogs_col}`), 0) AS cogs
				FROM `tabSalesDashBoard`
				WHERE `{date_col}` BETWEEN %s AND %s
				  {company_sql}
				  {cust_sql}
				""",
				tuple(params),
				as_dict=True,
			)
			if row:
				net_sales = float(row[0].net_sales or 0)
				cogs = float(row[0].cogs or 0)
				if net_sales > 0 or cogs > 0:
					return net_sales, cogs

	params_si: list[Any] = [from_date, to_date, customer]
	company_sql = ""
	if company:
		company_sql = " AND si.company = %s"
		params_si.append(company)

	sales_row = frappe.db.sql(
		f"""
		SELECT COALESCE(SUM(si.base_net_total), 0) AS net_sales
		FROM `tabSales Invoice` si
		WHERE si.docstatus = 1
		  AND si.posting_date BETWEEN %s AND %s
		  AND si.customer = %s
		  {company_sql}
		""",
		tuple(params_si),
		as_dict=True,
	)[0]
	net_sales = float(sales_row.net_sales or 0)

	cogs_params: list[Any] = [from_date, to_date, customer]
	cogs_company_sql = ""
	if company:
		cogs_company_sql = " AND si.company = %s"
		cogs_params.append(company)
	cogs_row = frappe.db.sql(
		f"""
		SELECT COALESCE(SUM(
			CASE WHEN sle.stock_value_difference < 0 THEN -sle.stock_value_difference ELSE 0 END
		), 0) AS cogs
		FROM `tabStock Ledger Entry` sle
		INNER JOIN `tabSales Invoice` si ON si.name = sle.voucher_no
		WHERE sle.voucher_type = 'Sales Invoice'
		  AND sle.is_cancelled = 0
		  AND sle.posting_date BETWEEN %s AND %s
		  AND si.docstatus = 1
		  AND si.customer = %s
		  {cogs_company_sql}
		""",
		tuple(cogs_params),
		as_dict=True,
	)[0]
	cogs = float(cogs_row.cogs or 0)
	return net_sales, cogs


def _customer_distinct_invoice_count(
	company: str,
	customer: str,
	from_date: date,
	to_date: date,
) -> int:
	cols = _sdb_customer_columns()
	if cols and "Invoice_No" in cols:
		company_sql = ""
		params: list[Any] = [from_date, to_date]
		if company and "Company" in cols:
			company_sql = " AND `Company` = %s"
			params.append(company)
		elif company and "company" in cols:
			company_sql = " AND company = %s"
			params.append(company)
		cust_sql, cust_params = _sdb_customer_scope_sql(customer)
		params.extend(cust_params)
		date_col = "Invoice_Date" if "Invoice_Date" in cols else "invoice_date"
		row = frappe.db.sql(
			f"""
			SELECT COUNT(DISTINCT `Invoice_No`) AS cnt
			FROM `tabSalesDashBoard`
			WHERE `{date_col}` BETWEEN %s AND %s
			  AND IFNULL(`Invoice_No`, '') != ''
			  {company_sql}
			  {cust_sql}
			""",
			tuple(params),
			as_dict=True,
		)
		if row and int(row[0].cnt or 0) > 0:
			return int(row[0].cnt)

	params_si: list[Any] = [from_date, to_date, customer]
	company_sql = ""
	if company:
		company_sql = " AND si.company = %s"
		params_si.append(company)
	row = frappe.db.sql(
		f"""
		SELECT COUNT(DISTINCT si.name) AS cnt
		FROM `tabSales Invoice` si
		WHERE si.docstatus = 1
		  AND si.is_return = 0
		  AND si.posting_date BETWEEN %s AND %s
		  AND si.customer = %s
		  {company_sql}
		""",
		tuple(params_si),
		as_dict=True,
	)[0]
	return int(row.cnt or 0)


def get_customer_sales_block(
	company: Optional[str] = None,
	customer: Optional[str] = None,
	as_of: Optional[str] = None,
) -> dict[str, Any]:
	"""Submitted-invoice net sales + GP (desk-aligned via SalesDashBoard when available)."""
	company = company or frappe.defaults.get_user_default("Company")
	empty = {
		"today": 0.0,
		"mtd": 0.0,
		"ytd": 0.0,
		"gp": 0.0,
		"gp_pct": 0.0,
		"avg_invoice": 0.0,
		"last_invoice_date": None,
	}
	if not company or not customer:
		return empty

	end = getdate(as_of or nowdate())
	today = getdate(nowdate())
	mtd_start = get_first_day(end)
	ytd_start = date(end.year, 1, 1)

	today_net, _ = _customer_net_and_cogs(company, customer, today, today)
	mtd_net, mtd_cogs = _customer_net_and_cogs(company, customer, mtd_start, end)
	ytd_net, ytd_cogs = _customer_net_and_cogs(company, customer, ytd_start, end)

	ytd_gp = round(ytd_net - ytd_cogs, 2)
	gp_pct = round(ytd_gp / ytd_net * 100, 2) if ytd_net > 0 else 0.0
	inv_count = _customer_distinct_invoice_count(company, customer, ytd_start, end)
	avg_invoice = round(ytd_net / inv_count, 2) if inv_count > 0 else 0.0

	last_inv = frappe.db.sql(
		"""
		SELECT MAX(si.posting_date) AS last_date
		FROM `tabSales Invoice` si
		WHERE si.docstatus = 1
		  AND si.company = %s
		  AND si.customer = %s
		""",
		(company, customer),
		as_dict=True,
	)[0].last_date

	return {
		"today": round(today_net, 2),
		"mtd": round(mtd_net, 2),
		"ytd": round(ytd_net, 2),
		"gp": ytd_gp,
		"gp_pct": gp_pct,
		"avg_invoice": avg_invoice,
		"last_invoice_date": str(last_inv) if last_inv else None,
	}


def _months_elapsed_ytd(as_of: date) -> int:
	"""Calendar months elapsed in as_of year (Jan = 1 … current month)."""
	return max(1, int(getdate(as_of).month))


def _customer_ytd_gross_sales(
	company: str,
	customer: str,
	from_date: date,
	to_date: date,
) -> float:
	"""Submitted invoice grand total (incl. VAT) — aligns with customer payments."""
	row = frappe.db.sql(
		"""
		SELECT COALESCE(SUM(si.base_grand_total), 0) AS total
		FROM `tabSales Invoice` si
		WHERE si.docstatus = 1
		  AND si.company = %s
		  AND si.customer = %s
		  AND si.posting_date BETWEEN %s AND %s
		""",
		(company, customer, from_date, to_date),
		as_dict=True,
	)[0]
	return float(row.total or 0)


def _customer_ytd_collections(
	company: str,
	customer: str,
	from_date: date,
	to_date: date,
) -> float:
	row = frappe.db.sql(
		"""
		SELECT COALESCE(SUM(pe.paid_amount), 0) AS total
		FROM `tabPayment Entry` pe
		WHERE pe.docstatus = 1
		  AND pe.payment_type = 'Receive'
		  AND pe.party_type = 'Customer'
		  AND pe.party = %s
		  AND pe.company = %s
		  AND pe.posting_date BETWEEN %s AND %s
		""",
		(customer, company, from_date, to_date),
		as_dict=True,
	)[0]
	return float(row.total or 0)


def get_customer_receivables_block(
	company: Optional[str] = None,
	customer: Optional[str] = None,
	chart_months: int = CHART_MONTHS,
	*,
	as_of: Optional[date] = None,
	ytd_sales: Optional[float] = None,
	ytd_collections: Optional[float] = None,
	months_elapsed: Optional[int] = None,
) -> dict[str, Any]:
	"""Receivables KPIs for Customer 360 (outstanding / overdue / current + YTD averages)."""
	company = company or frappe.defaults.get_user_default("Company")
	empty = {
		"outstanding": 0.0,
		"overdue": 0.0,
		"current": 0.0,
		"avg_monthly_sales": 0.0,
		"avg_monthly_paid": 0.0,
		"monthly_receivable": 0.0,
		"oldest_invoice": None,
	}
	if not company or not customer:
		return empty

	as_of = getdate(as_of or nowdate())
	row = frappe.db.sql(
		"""
		SELECT
			COALESCE(SUM(si.outstanding_amount), 0) AS outstanding,
			COALESCE(SUM(
				CASE WHEN COALESCE(si.due_date, si.posting_date) < %s
				THEN si.outstanding_amount ELSE 0 END
			), 0) AS overdue,
			MIN(CASE WHEN si.outstanding_amount > 0 THEN si.posting_date END) AS oldest_invoice
		FROM `tabSales Invoice` si
		WHERE si.docstatus = 1
		  AND si.outstanding_amount != 0
		  AND si.company = %s
		  AND si.customer = %s
		""",
		(as_of, company, customer),
		as_dict=True,
	)[0]

	outstanding = round(float(row.outstanding or 0), 2)
	overdue = round(float(row.overdue or 0), 2)
	current = round(max(outstanding - overdue, 0.0), 2)

	months = months_elapsed or _months_elapsed_ytd(as_of)
	ytd_start = date(as_of.year, 1, 1)
	if ytd_sales is None:
		ytd_sales = _customer_ytd_gross_sales(company, customer, ytd_start, as_of)
	if ytd_collections is None:
		ytd_collections = _customer_ytd_collections(company, customer, ytd_start, as_of)

	# Avg monthly sales: YTD invoice total incl. VAT (same basis as collections / trend table).
	avg_monthly_sales = round(float(ytd_sales or 0) / months, 2) if months else 0.0
	avg_monthly_paid = round(float(ytd_collections or 0) / months, 2) if months else 0.0

	oldest = row.oldest_invoice
	return {
		"outstanding": outstanding,
		"overdue": overdue,
		"current": current,
		"avg_monthly_sales": avg_monthly_sales,
		"avg_monthly_paid": avg_monthly_paid,
		"monthly_receivable": avg_monthly_paid,
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


def _ytd_month_periods(as_of: date) -> list[tuple[date, date, str]]:
	"""Calendar months from Jan through as_of month (desk YTD trend)."""
	as_of = getdate(as_of)
	periods: list[tuple[date, date, str]] = []
	cursor = date(as_of.year, 1, 1)
	while cursor.year == as_of.year and cursor.month <= as_of.month:
		month_start = getdate(get_first_day(cursor))
		month_end = getdate(get_last_day(month_start))
		if month_end > as_of:
			month_end = as_of
		periods.append((month_start, month_end, month_abbr[month_start.month]))
		cursor = getdate(add_months(get_first_day(month_start), 1))
	return periods


def _customer_monthly_sales_maps(
	company: str,
	customer: str,
	range_start: date,
	range_end: date,
) -> tuple[dict[tuple[int, int], float], dict[tuple[int, int], float]]:
	"""Net (desk GP / KPI) and gross (invoice total inc. VAT) by calendar month."""
	si_rows = frappe.db.sql(
		"""
		SELECT
			YEAR(si.posting_date) AS y,
			MONTH(si.posting_date) AS m,
			COALESCE(SUM(si.base_net_total), 0) AS net_sales,
			COALESCE(SUM(si.base_grand_total), 0) AS gross_sales
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
	si_net = {(int(r.y), int(r.m)): float(r.net_sales or 0) for r in si_rows}
	si_gross = {(int(r.y), int(r.m)): float(r.gross_sales or 0) for r in si_rows}

	net_map = dict(si_net)
	gross_map = dict(si_gross)

	cols = _sdb_customer_columns()
	if cols and "Invoice_No" in cols and "Net_Amount" in cols:
		date_col = "Invoice_Date" if "Invoice_Date" in cols else "invoice_date"
		sales_col = "Net_Amount" if "Net_Amount" in cols else "net_amount"
		gross_col = "Gross_Amount" if "Gross_Amount" in cols else None
		company_sql = ""
		params: list[Any] = [range_start, range_end]
		if company and "Company" in cols:
			company_sql = " AND `Company` = %s"
			params.append(company)
		cust_sql, cust_params = _sdb_customer_scope_sql(customer)
		params.extend(cust_params)
		gross_sel = (
			f", COALESCE(SUM(`{gross_col}`), 0) AS gross_sales"
			if gross_col and gross_col in cols
			else ", 0 AS gross_sales"
		)
		sdb_rows = frappe.db.sql(
			f"""
			SELECT
				YEAR(`{date_col}`) AS y,
				MONTH(`{date_col}`) AS m,
				COALESCE(SUM(`{sales_col}`), 0) AS net_sales
				{gross_sel}
			FROM `tabSalesDashBoard`
			WHERE `{date_col}` BETWEEN %s AND %s
			  {company_sql}
			  {cust_sql}
			GROUP BY YEAR(`{date_col}`), MONTH(`{date_col}`)
			""",
			tuple(params),
			as_dict=True,
		)
		for r in sdb_rows:
			key = (int(r.y), int(r.m))
			net_map[key] = float(r.net_sales or 0)

	# Invoice total (incl. VAT) always from submitted Sales Invoices.
	return net_map, gross_map


def get_customer_charts(
	company: Optional[str] = None,
	customer: Optional[str] = None,
	months: int = CHART_MONTHS,
	*,
	as_of: Optional[date] = None,
	ytd: bool = True,
	include_receivable_series: bool = False,
) -> dict[str, Any]:
	"""Monthly sales and collection series (YTD Jan→report month by default)."""
	company = company or frappe.defaults.get_user_default("Company")
	empty: dict[str, Any] = {
		"months": [],
		"sales": [],
		"sales_net": [],
		"sales_gross": [],
		"collection": [],
		"receivables": [],
		"sales_ly": [],
		"sales_growth_pct": [],
		"meta": {
			"sales_basis": "invoice_grand_total",
			"collection_basis": "payment_posting_date",
		},
	}
	if not company or not customer:
		return empty

	end = getdate(as_of or nowdate())
	periods = _ytd_month_periods(end) if ytd else _month_periods(end, months)
	if not periods:
		return empty

	range_start = periods[0][0]
	range_end = periods[-1][1]

	net_map, gross_map = _customer_monthly_sales_maps(company, customer, range_start, range_end)

	ly_start = date(end.year - 1, 1, 1)
	ly_end = date(end.year - 1, end.month, end.day)
	if end.month == 2 and end.day == 29:
		ly_end = date(end.year - 1, 2, 28)
	_, ly_gross_map = _customer_monthly_sales_maps(company, customer, ly_start, ly_end)

	collection_rows = frappe.db.sql(
		"""
		SELECT
			YEAR(pe.posting_date) AS y,
			MONTH(pe.posting_date) AS m,
			COALESCE(SUM(pe.paid_amount), 0) AS collected
		FROM `tabPayment Entry` pe
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
	sales_net: list[float] = []
	sales_gross: list[float] = []
	collection: list[float] = []
	receivables: list[float] = []
	sales_ly: list[float] = []
	sales_growth_pct: list[float | None] = []

	for month_start, month_end, label in periods:
		key = (month_start.year, month_start.month)
		ly_key = (end.year - 1, month_start.month)
		cur_net = round(net_map.get(key, 0.0), 2)
		cur_gross = round(gross_map.get(key, 0.0), 2)
		ly = round(ly_gross_map.get(ly_key, 0.0), 2)
		months_labels.append(label)
		sales.append(cur_gross)
		sales_net.append(cur_net)
		sales_gross.append(cur_gross)
		collection.append(round(collection_map.get(key, 0.0), 2))
		sales_ly.append(ly)
		if ly > 0:
			sales_growth_pct.append(round((cur_gross - ly) / ly * 100, 1))
		else:
			sales_growth_pct.append(None)
		if include_receivable_series:
			receivables.append(
				round(_receivable_as_of(company, customer, month_end), 2)
			)

	return {
		"months": months_labels,
		"sales": sales,
		"sales_net": sales_net,
		"sales_gross": sales_gross,
		"collection": collection,
		"receivables": receivables,
		"sales_ly": sales_ly,
		"sales_growth_pct": sales_growth_pct,
		"meta": {
			"sales_basis": "invoice_grand_total",
			"sales_net_basis": "net_ex_vat",
			"collection_basis": "payment_posting_date",
			"year": end.year,
		},
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
		"pdf_share_method": "erp_analysis.customer_notifications.get_statement_pdf",
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

	as_of_dt = getdate(to_date or nowdate())
	ytd_start = date(as_of_dt.year, 1, 1)
	months_elapsed = _months_elapsed_ytd(as_of_dt)

	sales = get_customer_sales_block(company=company, customer=customer_id, as_of=str(as_of_dt))
	ytd_gross = _customer_ytd_gross_sales(company, customer_id, ytd_start, as_of_dt)
	ytd_collections = _customer_ytd_collections(company, customer_id, ytd_start, as_of_dt)

	receivables = get_customer_receivables_block(
		company=company,
		customer=customer_id,
		as_of=as_of_dt,
		ytd_sales=ytd_gross,
		ytd_collections=ytd_collections,
		months_elapsed=months_elapsed,
	)
	charts = get_customer_charts(
		company=company,
		customer=customer_id,
		as_of=as_of_dt,
		ytd=True,
		include_receivable_series=False,
	)
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
		"sales": sales,
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
		"pdf_share_method": "erp_analysis.customer_notifications.get_statement_pdf",
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
		"sales": {
			"today": 0.0,
			"mtd": 0.0,
			"ytd": 0.0,
			"gp": 0.0,
			"gp_pct": 0.0,
			"avg_invoice": 0.0,
			"last_invoice_date": None,
		},
		"receivables": {
			"outstanding": 0.0,
			"overdue": 0.0,
			"current": 0.0,
			"avg_monthly_sales": 0.0,
			"avg_monthly_paid": 0.0,
			"monthly_receivable": 0.0,
			"oldest_invoice": None,
		},
		"charts": {
			"months": [],
			"sales": [],
			"sales_net": [],
			"sales_gross": [],
			"collection": [],
			"receivables": [],
			"sales_ly": [],
			"sales_growth_pct": [],
		},
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
