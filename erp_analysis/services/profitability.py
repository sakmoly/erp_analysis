"""Gross profit dashboard with dimensional breakdowns."""

from __future__ import annotations

from datetime import date
from typing import Any, List, Optional

import frappe
from frappe.utils import get_first_day, getdate, nowdate

from erp_analysis.permissions.access_profile import resolve_territory_scope, si_territory_sql
from erp_analysis.services.kpi.gross_profit import _gp_block, _sales_and_cogs, get_gross_profit_period_kpis


def _dashboard_columns() -> set[str]:
	if not frappe.db.table_exists("SalesDashBoard"):
		return set()
	try:
		return {c["Field"] for c in frappe.db.sql("SHOW COLUMNS FROM `tabSalesDashBoard`", as_dict=True)}
	except Exception:
		return set()


def _period_bounds(
	period: Optional[str] = None,
	from_date: Optional[str] = None,
	to_date: Optional[str] = None,
) -> tuple[date, date]:
	end = getdate(to_date or nowdate())
	if from_date:
		return getdate(from_date), end
	if (period or "mtd").lower() == "ytd":
		return date(end.year, 1, 1), end
	return get_first_day(end), end


def _breakdown_from_dashboard(
	company: Optional[str],
	start: date,
	end: date,
	dimension: str,
	limit: int,
	territories: Optional[List[str]] = None,
) -> list[dict[str, Any]]:
	cols = _dashboard_columns()
	if not cols:
		return []

	date_col = "Invoice_Date" if "Invoice_Date" in cols else "invoice_date"
	sales_col = "Net_Amount" if "Net_Amount" in cols else "net_amount"
	cogs_col = "COGS" if "COGS" in cols else "cogs"

	dim_map = {
		"territory": "Territory",
		"brand": "Brand",
		"division": "Division",
	}
	col = dim_map.get(dimension)
	if not col or col not in cols:
		return []

	company_sql = ""
	params: list[Any] = [start, end]
	if company and "company" in cols:
		company_sql = " AND company = %s"
		params.append(company)

	terr_sql, terr_params = "", []
	if territories and "Territory" in cols:
		terr_sql, terr_params = si_territory_sql(territories, field="Territory")
		params.extend(terr_params)

	rows = frappe.db.sql(
		f"""
		SELECT
			COALESCE(`{col}`, 'Unassigned') AS label,
			COALESCE(SUM(`{sales_col}`), 0) AS sales,
			COALESCE(SUM(`{cogs_col}`), 0) AS cogs
		FROM `tabSalesDashBoard`
		WHERE `{date_col}` BETWEEN %s AND %s
		  {company_sql}
		  {terr_sql}
		GROUP BY COALESCE(`{col}`, 'Unassigned')
		ORDER BY sales DESC
		LIMIT %s
		""",
		tuple([*params, int(limit)]),
		as_dict=True,
	)

	result = []
	for row in rows:
		sales = float(row.sales or 0)
		cogs = float(row.cogs or 0)
		gp, gp_pct = _gp_block(sales, cogs)
		result.append(
			{
				"label": row.label,
				"sales": round(sales, 2),
				"cogs": round(cogs, 2),
				"gross_profit": gp,
				"gp_pct": gp_pct,
			}
		)
	return result


def _breakdown_from_si(
	company: Optional[str],
	start: date,
	end: date,
	dimension: str,
	limit: int,
	territories: Optional[List[str]] = None,
) -> list[dict[str, Any]]:
	company_sql = ""
	params: list[Any] = [start, end]
	if company:
		company_sql = " AND si.company = %s"
		params.append(company)
	terr_sql, terr_params = si_territory_sql(territories, field="si.territory")
	params.extend(terr_params)

	if dimension == "territory":
		group_sql = "COALESCE(si.territory, 'Unassigned')"
	elif dimension == "brand":
		group_sql = "COALESCE(sii.brand, 'Unassigned')"
	else:
		group_sql = "COALESCE(i.item_group, 'Unassigned')"

	rows = frappe.db.sql(
		f"""
		SELECT
			{group_sql} AS label,
			COALESCE(SUM(sii.base_net_amount), 0) AS sales
		FROM `tabSales Invoice` si
		INNER JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
		LEFT JOIN `tabItem` i ON i.name = sii.item_code
		WHERE si.docstatus = 1
		  AND si.posting_date BETWEEN %s AND %s
		  {company_sql}
		  {terr_sql}
		GROUP BY {group_sql}
		ORDER BY sales DESC
		LIMIT %s
		""",
		tuple([*params, int(limit)]),
		as_dict=True,
	)

	result = []
	for row in rows:
		sales = float(row.sales or 0)
		gp, gp_pct = _gp_block(sales, 0)
		result.append(
			{
				"label": row.label,
				"sales": round(sales, 2),
				"cogs": 0,
				"gross_profit": gp,
				"gp_pct": gp_pct,
			}
		)
	return result


def get_dimension_breakdown(
	company: Optional[str],
	start: date,
	end: date,
	dimension: str,
	limit: int = 10,
	territories: Optional[List[str]] = None,
) -> list[dict[str, Any]]:
	rows = _breakdown_from_dashboard(company, start, end, dimension, limit, territories)
	if rows:
		return rows
	return _breakdown_from_si(company, start, end, dimension, limit, territories)


def get_gross_profit_dashboard_payload(
	company: Optional[str] = None,
	period: Optional[str] = None,
	from_date: Optional[str] = None,
	to_date: Optional[str] = None,
	limit: int = 10,
	territories: Optional[List[str]] = None,
) -> dict[str, Any]:
	start, end = _period_bounds(period, from_date, to_date)
	if territories is None:
		territories = resolve_territory_scope(company=company, purpose="view", module="sales")
	period_sales, period_cogs = _sales_and_cogs(company, start, end, territories)
	period_gp, period_gp_pct = _gp_block(period_sales, period_cogs)

	return {
		"period": {"from_date": str(start), "to_date": str(end)},
		"kpis": {
			**get_gross_profit_period_kpis(company=company, as_of=end, territories=territories),
			"period_sales": round(period_sales, 2),
			"period_cogs": round(period_cogs, 2),
			"period_gp": period_gp,
			"period_gp_pct": period_gp_pct,
		},
		"by_territory": get_dimension_breakdown(company, start, end, "territory", limit, territories),
		"by_brand": get_dimension_breakdown(company, start, end, "brand", limit, territories),
		"by_division": get_dimension_breakdown(company, start, end, "division", limit, territories),
	}
