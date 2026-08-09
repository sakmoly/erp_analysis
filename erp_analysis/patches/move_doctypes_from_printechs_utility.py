import frappe

DOCTYPES = [
	"Access Profile",
	"Access Profile Line",
	"Access Profile Territory",
	"Access Object Registry",
	"E Catalogue",
	"E Catalogue Video",
	"Mobile Push Token",
]


def execute():
	for doctype in DOCTYPES:
		if frappe.db.exists("DocType", doctype):
			frappe.db.set_value("DocType", doctype, "module", "ERP Analysis")

	frappe.db.commit()
