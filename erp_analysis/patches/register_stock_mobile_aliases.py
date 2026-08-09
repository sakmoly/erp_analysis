import frappe

from erp_analysis.mobile_config import clear_mobile_config_cache


STOCK_ALIASES = (
	("erp_analysis.stock.get_inventory_hierarchy", "Inventory Hierarchy (stock alias)"),
)


def execute():
	for object_key, label in STOCK_ALIASES:
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
	clear_mobile_config_cache()
