"""Sales KPI helpers — today / MTD / YTD with optional LY compare."""

from __future__ import annotations

from datetime import date
from typing import Any, List, Optional

import frappe
from frappe.utils import add_years, get_first_day, getdate, nowdate

from erp_analysis.permissions.access_profile import resolve_territory_scope, si_territory_sql


def _sum_net_sales(
	company: Optional[str],
	from_date: date,
	to_date: date,
	territories: Optional[List[str]] = None,
) -> float:
	params: list[Any] = [from_date, to_date]
	company_sql = ""
	if company:
		company_sql = " AND company = %s"
		params.append(company)
	terr_sql, terr_params = si_territory_sql(territories, field="territory")
	params.extend(terr_params)

	result = frappe.db.sql(
		f"""
		SELECT COALESCE(SUM(base_net_total), 0)
		FROM `tabSales Invoice`
		WHERE docstatus = 1
		  AND posting_date BETWEEN %s AND %s
		  {company_sql}
		  {terr_sql}
		""",
		tuple(params),
	)[0][0]
	return float(result or 0)


def get_sales_period_kpis(
	company: Optional[str] = None,
	as_of: Optional[str] = None,
	territory: Optional[str] = None,
	territories: Optional[List[str]] = None,
) -> dict[str, Any]:
	"""Return today, MTD, YTD and last-year comparisons for executive dashboard."""
	today = getdate(as_of or nowdate())
	mtd_start = get_first_day(today)
	ytd_start = date(today.year, 1, 1)

	mtd_end_ly = add_years(today, -1)
	mtd_start_ly = get_first_day(mtd_end_ly)
	ytd_start_ly = date(mtd_end_ly.year, 1, 1)

	if territories is not None:
		scope = territories
	else:
		scope = resolve_territory_scope(
			requested=territory, company=company, purpose="view", module="sales"
		)

	today_val = _sum_net_sales(company, today, today, scope)
	mtd_val = _sum_net_sales(company, mtd_start, today, scope)
	ytd_val = _sum_net_sales(company, ytd_start, today, scope)
	mtd_ly = _sum_net_sales(company, mtd_start_ly, mtd_end_ly, scope)
	ytd_ly = _sum_net_sales(company, ytd_start_ly, mtd_end_ly, scope)

	def _pct(curr: float, prev: float) -> float:
		if not prev:
			return 0.0
		return round((curr - prev) / prev * 100, 2)

	return {
		"today": round(today_val, 2),
		"mtd": round(mtd_val, 2),
		"ytd": round(ytd_val, 2),
		"mtd_ly": round(mtd_ly, 2),
		"ytd_ly": round(ytd_ly, 2),
		"mtd_change_pct": _pct(mtd_val, mtd_ly),
		"ytd_change_pct": _pct(ytd_val, ytd_ly),
	}
