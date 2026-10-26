"""Verify open SO KPI access for sakeer@printechs.com."""

from __future__ import annotations

import json

import frappe

from erp_analysis.services.mobile_widgets import get_dashboard_board_data, get_dashboard_widget_data


def main():
	user = "sakeer@printechs.com"
	company = "Printechs Advanced Printing Trading Co."
	frappe.set_user(user)
	filters = json.dumps({"territory": ["Dammam"]})
	board = get_dashboard_board_data(
		dashboard_id="sales_overview",
		company=company,
		filters=filters,
		territory="Dammam",
		refresh=1,
	)
	kpi = board.get("widgets", {}).get("sales_orders_kpi")
	print("user", user, "kpi", (kpi or {}).get("value"))
	list_w = get_dashboard_widget_data(
		widget_key="sales_open_orders_list",
		company=company,
		filters=filters,
		drill_depth=1,
		limit=3,
	)
	print("list_rows", len((list_w.get("table") or {}).get("rows") or []))


if __name__ == "__main__":
	main()
