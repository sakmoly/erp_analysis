import os
import shutil
import socket
import zipfile

import frappe

WEBSITE_CATALOGUE_ROOT = "/home/erpnext/frappe-bench/apps/printechs_website/printechs_website/www/catalogue"


def _unzip_catalogue(doc):
	if not getattr(doc, "flip_package", None):
		frappe.msgprint("No Flip Package (ZIP) attached.", alert=True)
		return

	file_doc = frappe.get_doc("File", {"file_url": doc.flip_package})
	zip_path = os.path.abspath(file_doc.get_full_path())

	if not os.path.exists(zip_path):
		frappe.throw(f"ZIP not found on server: {zip_path}")

	if not zip_path.lower().endswith(".zip"):
		frappe.throw("Attached file is not a ZIP.")

	output_dir = os.path.join(WEBSITE_CATALOGUE_ROOT, doc.name)

	if os.path.exists(output_dir):
		shutil.rmtree(output_dir)

	os.makedirs(output_dir, exist_ok=True)

	with zipfile.ZipFile(zip_path, "r") as zf:
		zf.extractall(output_dir)

	frappe.msgprint(f"Unzipped to /catalogue/{doc.name}/", alert=True)


def after_save(doc, method=None):
	_unzip_catalogue(doc)


@frappe.whitelist()
def unzip_catalogue(catalogue_id: str):
	doc = frappe.get_doc("E Catalogue", catalogue_id)
	_unzip_catalogue(doc)
	return {"message": "OK"}
