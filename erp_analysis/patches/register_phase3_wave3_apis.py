import frappe


PHASE3_WAVE3_APIS = (
	("erp_analysis.sales_orders.get_order_book_dashboard", "Order Book Dashboard"),
	("erp_analysis.sales_orders.get_open_sales_orders", "Open Sales Orders"),
)


def execute():
	for object_key, label in PHASE3_WAVE3_APIS:
		if frappe.db.exists("Access Object Registry", {"object_key": object_key}):
			continue
		doc = frappe.get_doc(
			{
				"doctype": "Access Object Registry",
				"object_type": "API",
				"object_key": object_key,
				"label": label,
				"is_active": 1,
			}
		)
		doc.insert(ignore_permissions=True)

	frappe.db.commit()
