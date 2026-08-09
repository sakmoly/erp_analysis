import frappe


def execute():
	rows = frappe.get_all("Access Object Registry", fields=["name", "object_key"])
	for row in rows:
		key = row.object_key or ""
		if "printechs_utility" in key:
			frappe.db.set_value(
				"Access Object Registry",
				row.name,
				"object_key",
				key.replace("printechs_utility", "erp_analysis"),
			)

	frappe.db.commit()
