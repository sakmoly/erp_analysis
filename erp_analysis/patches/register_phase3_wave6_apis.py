import frappe


PHASE3_WAVE6_APIS = (
	("erp_analysis.inventory.get_stock_cover", "Stock Cover"),
	("erp_analysis.profitability.get_gross_profit_dashboard", "Gross Profit Dashboard"),
	("erp_analysis.exceptions.get_management_exceptions", "Management Exceptions"),
	("erp_analysis.approval_analytics.get_approval_summary", "Approval Analytics"),
)


def execute():
	for object_key, label in PHASE3_WAVE6_APIS:
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
