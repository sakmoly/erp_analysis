import json

import frappe

from erp_analysis.services.mobile_widgets import get_dashboard_widget_data


def main():
	frappe.set_user("sakeer@printechs.com")
	company = "Printechs Advanced Printing Trading Co."
	filters = json.dumps({"territory": ["Dammam"]})
	w = get_dashboard_widget_data(
		widget_key="sales_open_orders_list",
		company=company,
		filters=filters,
		drill_depth=1,
		limit=2,
	)
	print("L1", json.dumps(w["rows"][0], default=str, indent=2))
	filters2 = json.dumps({"territory": ["Dammam"], "sales_order": ["SOD26-000001"]})
	w2 = get_dashboard_widget_data(
		widget_key="sales_open_orders_list",
		company=company,
		filters=filters2,
		drill_depth=2,
		limit=5,
	)
	if w2.get("rows"):
		print("L2", json.dumps(w2["rows"][0], default=str, indent=2))
