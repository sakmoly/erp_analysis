import frappe


PHASE3_WAVE4_APIS = (
	("erp_analysis.payables.get_payables_dashboard", "Payables Dashboard"),
	("erp_analysis.payables.get_payment_planning", "Payment Planning"),
	("erp_analysis.purchase.get_purchase_dashboard", "Purchase Dashboard"),
	("erp_analysis.purchase.get_open_purchase_orders", "Open Purchase Orders"),
)


def execute():
	for object_key, label in PHASE3_WAVE4_APIS:
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
