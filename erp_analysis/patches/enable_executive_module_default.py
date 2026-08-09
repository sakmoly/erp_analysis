import frappe

from erp_analysis.mobile_config import clear_mobile_config_cache


def execute():
	if not frappe.db.exists("DocType", "Mobile App Settings"):
		return

	if frappe.db.exists("Mobile App Settings", "Mobile App Settings"):
		frappe.db.set_value(
			"Mobile App Settings",
			"Mobile App Settings",
			"module_executive",
			1,
			update_modified=False,
		)
		frappe.db.commit()
		clear_mobile_config_cache()
