import frappe


def after_install():
	try:
		from erp_analysis.oauth_setup import ensure_oauth_client

		ensure_oauth_client()
	except Exception:
		frappe.log_error(frappe.get_traceback(), "erp_analysis.after_install")


def after_migrate():
	try:
		from erp_analysis.oauth_setup import ensure_oauth_client

		ensure_oauth_client()
	except Exception:
		frappe.log_error(frappe.get_traceback(), "erp_analysis.after_migrate")
