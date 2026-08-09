import frappe

from erp_analysis.mobile_config import clear_mobile_config_cache


LEGACY_INVENTORY_PATHS = (
	("printechs_utility.inventory.get_inventory_hierarchy", "Inventory Hierarchy (legacy mobile path)"),
	("printechs_utility.inventory.get_inventory_snapshot", "Inventory Snapshot (legacy mobile path)"),
	("printechs_utility.inventory.get_inventory_items", "Inventory Items (legacy mobile path)"),
	("erp_analysis.stock.get_inventory_items", "Inventory Items (stock alias)"),
	("erp_analysis.inventory.get_inventory_items", "Inventory Items"),
)


def execute():
	for object_key, label in LEGACY_INVENTORY_PATHS:
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
