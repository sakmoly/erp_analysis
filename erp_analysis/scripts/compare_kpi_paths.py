"""Compare legacy vs batch KPI paths for mobile debugging."""

from __future__ import annotations

import frappe


def run(user: str = "sakeer@printechs.com", company: str = "Printechs Advanced Printing Trading Co."):
	frappe.set_user(user)
	from erp_analysis.sales_kpis import get_dashboard_kpis
	from erp_analysis.services.analytics_sales import get_dashboard_sales_kpi, get_sales_kpi

	legacy = get_dashboard_kpis(company=company)
	msg = legacy.get("message") or legacy
	print("legacy get_dashboard_kpis sales_ytd:", (msg.get("sales") or {}).get("ytd"))

	batch_dash = get_dashboard_sales_kpi(
		user=user, company=company, metric="net_sales", period="ytd", compare="ly"
	)
	print("get_dashboard_sales_kpi ytd:", batch_dash.get("value"))

	si = get_sales_kpi(user=user, company=company, metric="net_sales", period="ytd", compare="ly")
	print("get_sales_kpi (SI) ytd:", si.get("value"))

	board = frappe.call(
		"erp_analysis.api.get_dashboard_board_data",
		dashboard_id="sales_overview",
		company=company,
		period="ytd",
		refresh=1,
		use_cache=0,
	)
	w = (board.get("widgets") or {}).get("sales_total_kpi") or {}
	print("board sales_total_kpi:", w.get("value"), "meta=", w.get("meta"))

	frappe.set_user("Administrator")
