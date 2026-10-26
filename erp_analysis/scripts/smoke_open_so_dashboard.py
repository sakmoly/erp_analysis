"""Smoke: sales_orders_kpi + sales_open_orders_list drill."""

from __future__ import annotations

import json

import frappe

from erp_analysis.services.mobile_widgets import get_dashboard_board_data, get_dashboard_widget_data


def main():
	frappe.set_user("Administrator")
	company = frappe.db.get_single_value("Global Defaults", "default_company")
	if not company:
		company = "Printechs Advanced Printing Trading Co."
	filters = json.dumps({"territory": ["Dammam"]})
	board = get_dashboard_board_data(
		dashboard_id="sales_overview",
		company=company,
		filters=filters,
		territory="Dammam",
		refresh=1,
	)
	kpi = board.get("widgets", {}).get("sales_orders_kpi")
	print("kpi", kpi.get("value") if kpi else None, (kpi or {}).get("config"))
	list_w = get_dashboard_widget_data(
		widget_key="sales_open_orders_list",
		company=company,
		filters=filters,
		drill_depth=1,
		limit=5,
	)
	rows = (list_w.get("table") or {}).get("rows") or []
	print("list_count", len(rows))
	if rows:
		so = rows[0].get("label")
		items = get_dashboard_widget_data(
			widget_key="sales_open_orders_list",
			company=company,
			filters=json.dumps({"territory": ["Dammam"], "sales_order": [so]}),
			drill_depth=2,
			limit=20,
		)
		print("items", len((items.get("table") or {}).get("rows") or []), "so", so)


if __name__ == "__main__":
	main()
