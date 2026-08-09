import frappe


PHASE3_WAVE2_APIS = (
	("erp_analysis.executive.get_executive_dashboard", "Executive Dashboard"),
	("erp_analysis.collection.get_collection_dashboard", "Collection Dashboard"),
	("erp_analysis.collection.get_collection_attention", "Collection Attention"),
	("erp_analysis.sales_performance.get_salesperson_ranking", "Salesperson Ranking"),
	("erp_analysis.sales_performance.get_product_ranking", "Product Ranking"),
)


def execute():
	for object_key, label in PHASE3_WAVE2_APIS:
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
