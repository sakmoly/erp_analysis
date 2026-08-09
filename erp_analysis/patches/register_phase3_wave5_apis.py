import frappe


PHASE3_WAVE5_APIS = (
	("erp_analysis.customer_360.get_customer_360", "Customer 360"),
)


def execute():
	for object_key, label in PHASE3_WAVE5_APIS:
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
