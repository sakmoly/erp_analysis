import frappe

from erp_analysis.mobile_config import clear_mobile_config_cache


SALES_PERFORMANCE_ALIASES = (
	("erp_analysis.sales.get_salesperson_performance", "Salesperson Performance"),
	("erp_analysis.sales.get_product_performance", "Product Performance"),
	("erp_analysis.sales_performance.get_salesperson_performance", "Salesperson Performance"),
	("erp_analysis.sales_performance.get_product_performance", "Product Performance"),
	("erp_analysis.sales_kpis.get_salesperson_performance", "Salesperson Performance (sales_kpis alias)"),
	("erp_analysis.sales_kpis.get_product_performance", "Product Performance (sales_kpis alias)"),
)


def execute():
	for object_key, label in SALES_PERFORMANCE_ALIASES:
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

	if frappe.db.exists("Mobile App Settings", "Mobile App Settings"):
		frappe.db.set_value(
			"Mobile App Settings",
			"Mobile App Settings",
			"module_sales_performance",
			1,
			update_modified=False,
		)

	frappe.db.commit()
	clear_mobile_config_cache()
