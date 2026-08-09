"""Gross profit KPIs — MTD / YTD and GP %."""

from __future__ import annotations

from datetime import date
from typing import Any, List, Optional

import frappe
from frappe.utils import get_first_day, getdate, nowdate

from erp_analysis.permissions.access_profile import resolve_territory_scope, si_territory_sql


def _sales_and_cogs_si(
	company: Optional[str],
	from_date: date,
	to_date: date,
	territories: Optional[List[str]] = None,
) -> tuple[float, float]:
	"""Sales Invoice net total + COGS from Stock Ledger (Sales Invoice vouchers)."""
	params: list[Any] = [from_date, to_date]
	company_sql = ""
	if company:
		company_sql = " AND si.company = %s"
		params.append(company)
	terr_sql, terr_params = si_territory_sql(territories, field="si.territory")
	params.extend(terr_params)

	sales_row = frappe.db.sql(
		f"""
		SELECT COALESCE(SUM(si.base_net_total), 0) AS sales
		FROM `tabSales Invoice` si
		WHERE si.docstatus = 1
		  AND si.posting_date BETWEEN %s AND %s
		  {company_sql}
		  {terr_sql}
		""",
		tuple(params),
		as_dict=True,
	)[0]
	sales = float(sales_row.sales or 0)

	# COGS: join SI for territory scope when restricted
	cogs_params: list[Any] = [from_date, to_date]
	cogs_company_sql = ""
	if company:
		cogs_company_sql = " AND sle.company = %s"
		cogs_params.append(company)
	cogs_join = ""
	cogs_terr_sql = ""
	if territories:
		cogs_join = " INNER JOIN `tabSales Invoice` si ON si.name = sle.voucher_no "
		cogs_terr_sql, cogs_terr_params = si_territory_sql(territories, field="si.territory")
		cogs_params.extend(cogs_terr_params)

	cogs_row = frappe.db.sql(
		f"""
		SELECT COALESCE(SUM(
			CASE WHEN sle.stock_value_difference < 0 THEN -sle.stock_value_difference ELSE 0 END
		), 0) AS cogs
		FROM `tabStock Ledger Entry` sle
		{cogs_join}
		WHERE sle.voucher_type = 'Sales Invoice'
		  AND sle.is_cancelled = 0
		  AND sle.posting_date BETWEEN %s AND %s
		  {cogs_company_sql}
		  {cogs_terr_sql}
		""",
		tuple(cogs_params),
		as_dict=True,
	)[0]
	cogs = float(cogs_row.cogs or 0)
	return sales, cogs


def _sales_and_cogs_dashboard(
	company: Optional[str],
	from_date: date,
	to_date: date,
	territories: Optional[List[str]] = None,
) -> tuple[float, float]:
	"""Printechs custom SalesDashBoard table when present."""
	if not frappe.db.table_exists("SalesDashBoard"):
		return 0.0, 0.0

	try:
		cols = {c["Field"] for c in frappe.db.sql("SHOW COLUMNS FROM `tabSalesDashBoard`", as_dict=True)}
	except Exception:
		cols = set()

	company_sql = ""
	params: list[Any] = [from_date, to_date]
	if company and "Company" in cols:
		company_sql = " AND `Company` = %s"
		params.append(company)
	elif company and "company" in cols:
		company_sql = " AND company = %s"
		params.append(company)

	terr_sql, terr_params = "", []
	if territories and "Territory" in cols:
		terr_sql, terr_params = si_territory_sql(territories, field="Territory")
		params.extend(terr_params)

	sales_col = "Net_Amount" if "Net_Amount" in cols else "net_amount"
	cogs_col = "COGS" if "COGS" in cols else "cogs"
	date_col = "Invoice_Date" if "Invoice_Date" in cols else "invoice_date"

	row = frappe.db.sql(
		f"""
		SELECT
			COALESCE(SUM(`{sales_col}`), 0) AS sales,
			COALESCE(SUM(`{cogs_col}`), 0) AS cogs
		FROM `tabSalesDashBoard`
		WHERE `{date_col}` BETWEEN %s AND %s
		  {company_sql}
		  {terr_sql}
		""",
		tuple(params),
		as_dict=True,
	)
	if not row:
		return 0.0, 0.0
	return float(row[0].sales or 0), float(row[0].cogs or 0)


def _sales_and_cogs(
	company: Optional[str],
	from_date: date,
	to_date: date,
	territories: Optional[List[str]] = None,
) -> tuple[float, float]:
	try:
		sales, cogs = _sales_and_cogs_dashboard(company, from_date, to_date, territories)
		if sales > 0 or cogs > 0:
			return sales, cogs
	except Exception:
		frappe.log_error(title="kpi.gross_profit.dashboard", message=frappe.get_traceback())
	return _sales_and_cogs_si(company, from_date, to_date, territories)


def _gp_block(sales: float, cogs: float) -> tuple[float, float]:
	gp = sales - cogs
	gp_pct = round(gp / sales * 100, 2) if sales > 0 else 0.0
	return round(gp, 2), gp_pct


def get_gross_profit_period_kpis(
	company: Optional[str] = None,
	as_of: Optional[str] = None,
	territory: Optional[str] = None,
	territories: Optional[List[str]] = None,
) -> dict[str, Any]:
	today = getdate(as_of or nowdate())
	mtd_start = get_first_day(today)
	ytd_start = date(today.year, 1, 1)
	if territories is not None:
		scope = territories
	else:
		scope = resolve_territory_scope(
			requested=territory, company=company, purpose="view", module="sales"
		)

	mtd_sales, mtd_cogs = _sales_and_cogs(company, mtd_start, today, scope)
	ytd_sales, ytd_cogs = _sales_and_cogs(company, ytd_start, today, scope)
	mtd_gp, mtd_pct = _gp_block(mtd_sales, mtd_cogs)
	ytd_gp, ytd_pct = _gp_block(ytd_sales, ytd_cogs)

	return {
		"mtd": mtd_gp,
		"ytd": ytd_gp,
		"gp_pct_mtd": mtd_pct,
		"gp_pct_ytd": ytd_pct,
	}
