import frappe

from erp_analysis.mobile_config import MODULE_FIELDS, clear_mobile_config_cache


def execute():
	if not frappe.db.exists("DocType", "Mobile App Settings"):
		return

	settings = frappe.get_single("Mobile App Settings")
	changed = False

	for fieldname in MODULE_FIELDS.values():
		if not settings.meta.has_field(fieldname):
			continue
		if not settings.get(fieldname):
			settings.set(fieldname, 1)
			changed = True

	if changed:
		settings.save(ignore_permissions=True)

	frappe.db.commit()
	clear_mobile_config_cache()
