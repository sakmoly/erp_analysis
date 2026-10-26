"""
Smoke: division list, drill to sub_group, reconcile KPI vs sum(division).

Run:
  bench --site <site> execute erp_analysis.scripts.sales_division_drill_smoke.run
"""

from __future__ import annotations

import json

import frappe
from frappe.utils import flt, getdate

COMPANY = "Printechs Advanced Printing Trading Co."
USER = "sakeer@printechs.com"
FROM_DATE = "2026-01-01"
TO_DATE = "2026-10-13"
PERIOD = "ytd"


def _widget_rows(widget: dict) -> list:
	if not widget:
		return []
	if widget.get("table", {}).get("rows"):
		return widget["table"]["rows"]
	if widget.get("chart", {}).get("series"):
		return widget["chart"]["series"]
	return widget.get("rows") or []


def _row_value(row: dict) -> float:
	return flt(row.get("value") or row.get("metric") or row.get("amount") or row.get("total_sales"))


def _kpi_value(widget: dict) -> float:
	if not widget:
		return 0.0
	for key in ("value", "net_sales", "total_sales"):
		if widget.get(key) is not None:
			return flt(widget.get(key))
	if widget.get("kpis"):
		return flt((widget["kpis"][0] or {}).get("value"))
	if widget.get("kpi"):
		return flt((widget["kpi"] or {}).get("value"))
	return 0.0


def run():
	frappe.set_user(USER)

	board = frappe.call(
		"erp_analysis.api.get_dashboard_board_data",
		dashboard_id="sales_overview",
		company=COMPANY,
		from_date=FROM_DATE,
		to_date=TO_DATE,
		period=PERIOD,
	)
	widgets = (board or {}).get("widgets") or {}

	kpi_w = widgets.get("sales_total_kpi") or widgets.get("sales_dash_net_ytd_kpi") or {}
	kpi_val = _kpi_value(kpi_w)

	div_rows = _widget_rows(widgets.get("sales_by_division")) or _widget_rows(
		widgets.get("sales_donut_division")
	)
	div_sum = sum(_row_value(r) for r in div_rows)

	print("=== Board batch (mobile §1) ===")
	print("KPI total:", kpi_val)
	print("Division rows:", len(div_rows), "sum:", div_sum, "gap:", kpi_val - div_sum)
	for row in div_rows:
		print(" ", row.get("label") or row.get("dimension_value"), _row_value(row))

	# Exact mobile drill body (All Territories + view_territories list)
	drill_filters = json.dumps(
		{
			"division": ["Industrial"],
			"territory": ["Dammam", "Riyadh", "Jeddah"],
		},
		separators=(",", ":"),
	)
	drill = frappe.call(
		"erp_analysis.api.get_dashboard_widget_data",
		widget_key="sales_by_division",
		company=COMPANY,
		from_date=FROM_DATE,
		to_date=TO_DATE,
		period=PERIOD,
		limit=10,
		dimension="sub_group",
		drill_depth=1,
		filters=drill_filters,
		territories="Dammam,Riyadh,Jeddah",
		show_ly=0,
	)
	drill_rows = _widget_rows(drill)
	print("\n=== Drill Industrial → sub_group (mobile §2) ===")
	print("top-level rows:", len(drill.get("rows") or []))
	print("table.rows:", len((drill.get("table") or {}).get("rows") or []))
	print("effective rows:", len(drill_rows))
	for row in drill_rows:
		print(" ", row.get("label") or row.get("dimension"), _row_value(row))

	if frappe.db.table_exists("SalesDashBoard"):
		from erp_analysis.permissions.access_profile import get_view_territories

		scope = get_view_territories(USER, COMPANY, expand=True) or []
		cond = "Invoice_Date BETWEEN %s AND %s"
		params: list = [FROM_DATE, TO_DATE]
		if scope:
			cond += " AND Territory IN %s"
			params.append(tuple(scope))

		total = flt(
			frappe.db.sql(
				f"SELECT COALESCE(SUM(Net_Amount), 0) FROM `tabSalesDashBoard` WHERE {cond}",
				params,
			)[0][0]
		)
		by_div = frappe.db.sql(
			f"""
			SELECT COALESCE(Division, '(blank)') AS division, SUM(Net_Amount) AS sales
			FROM `tabSalesDashBoard`
			WHERE {cond}
			GROUP BY COALESCE(Division, '(blank)')
			ORDER BY sales DESC
			""",
			params,
			as_dict=True,
		)
		div_sql_sum = sum(flt(r.sales) for r in by_div if r.division != "(blank)")
		blank = next((r for r in by_div if r.division == "(blank)"), None)

		print("\n=== SQL SalesDashBoard (Net_Amount, view scope) ===")
		print("scope territories:", scope)
		print("Grand total:", total)
		print("Sum division (non-blank):", div_sql_sum)
		print("Blank division:", flt(blank.sales) if blank else 0)
		for row in by_div[:12]:
			print(f"  {row.division}: {flt(row.sales):,.2f}")

	frappe.set_user("Administrator")
