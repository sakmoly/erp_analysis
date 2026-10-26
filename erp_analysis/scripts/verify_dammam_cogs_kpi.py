"""Verify sales overview KPIs align for Dammam territory filter."""

from __future__ import annotations

import json

import frappe

from erp_analysis.services.mobile_widgets import get_dashboard_board_data


def main():
	user = "sakeer@printechs.com"
	company = "Printechs Advanced Printing Trading Co."
	frappe.set_user(user)
	filters = json.dumps({"territory": ["Dammam"]})
	from erp_analysis.services.mobile_widgets import clear_dashboard_board_cache

	clear_dashboard_board_cache()
	board = get_dashboard_board_data(
		dashboard_id="sales_overview",
		company=company,
		filters=filters,
		territory="Dammam",
		period="ytd",
		show_ly=1,
		refresh=1,
		use_cache=0,
	)
	widgets = board.get("widgets") or {}
	for key in ("sales_total_kpi", "sales_cogs_kpi", "sales_gp_kpi", "sales_gp_margin_kpi"):
		w = widgets.get(key) or {}
		val = w.get("value")
		if val is None and w.get("kpis"):
			val = (w["kpis"][0] or {}).get("value")
		meta = w.get("meta") or {}
		print(
			key,
			"value=",
			val,
			"cogs_root=",
			w.get("cogs"),
			"gp_root=",
			w.get("gross_profit"),
			"period=",
			meta.get("period"),
			"from=",
			meta.get("from_date"),
		)


if __name__ == "__main__":
	main()
