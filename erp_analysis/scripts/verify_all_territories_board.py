"""Verify All Territories board: KPI ~SI total, division sum matches."""

from __future__ import annotations

import frappe
from frappe.utils import flt


def run(user: str = "sakeer@printechs.com", company: str = "Printechs Advanced Printing Trading Co."):
	frappe.set_user(user)
	board = frappe.call(
		"erp_analysis.api.get_dashboard_board_data",
		dashboard_id="sales_overview",
		company=company,
		from_date="2026-01-01",
		to_date="2026-10-13",
		period="ytd",
		refresh=1,
	)
	w = board.get("widgets") or {}
	kpi = w.get("sales_total_kpi") or {}
	div = w.get("sales_by_division") or {}
	kpi_v = flt(kpi.get("value") or (kpi.get("kpi") or {}).get("value"))
	rows = div.get("table", {}).get("rows") or div.get("chart", {}).get("series") or div.get("rows") or []
	div_sum = sum(flt(r.get("metric") or r.get("value")) for r in rows)
	print("KPI:", kpi_v, "meta.data_source:", (kpi.get("meta") or {}).get("data_source"))
	print("Division rows:", len(rows), "sum:", div_sum, "gap:", kpi_v - div_sum)
	for r in rows:
		print(" ", r.get("dimension") or r.get("label"), flt(r.get("metric") or r.get("value")))
	frappe.set_user("Administrator")
