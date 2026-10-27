import frappe


def after_install():
	try:
		from erp_analysis.oauth_setup import ensure_oauth_client

		ensure_oauth_client()
	except Exception:
		frappe.log_error(frappe.get_traceback(), "erp_analysis.after_install")

	try:
		from erp_analysis.patches.ensure_sales_dashboard_table import ensure_sales_dashboard_table

		ensure_sales_dashboard_table(apply_view=True)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "erp_analysis.after_install.sales_dashboard")

	try:
		from erp_analysis.patches.ensure_erp_analysis_desk_workspace import ensure_erp_analysis_desk_workspace

		ensure_erp_analysis_desk_workspace()
	except Exception:
		frappe.log_error(frappe.get_traceback(), "erp_analysis.after_install.desk_workspace")


def after_migrate():
	try:
		from erp_analysis.oauth_setup import ensure_oauth_client

		ensure_oauth_client()
	except Exception:
		frappe.log_error(frappe.get_traceback(), "erp_analysis.after_migrate")

	try:
		from erp_analysis.patches.ensure_sales_dashboard_table import ensure_sales_dashboard_table

		ensure_sales_dashboard_table(apply_view=True)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "erp_analysis.after_migrate.sales_dashboard")

	try:
		from erp_analysis.patches.ensure_erp_analysis_desk_workspace import ensure_erp_analysis_desk_workspace

		ensure_erp_analysis_desk_workspace()
	except Exception:
		frappe.log_error(frappe.get_traceback(), "erp_analysis.after_migrate.desk_workspace")
