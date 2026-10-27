app_name = "erp_analysis"
app_title = "ERP Analysis"
app_publisher = "Printechs"
app_description = "Mobile Business Analysis APIs for ERPNext"
app_email = "support@printechs.com"
app_license = "mit"

# required_apps = ["erpnext"]

# Includes in <head>
# ------------------

# Home Pages
# ----------

# Generators
# ----------

# Jinja
# ----------

# Installation
# ------------
# before_install = "erp_analysis.install.before_install"
# after_install / after_migrate: OAuth + SalesDashBoard table (idempotent).
# If migrate hangs on locks, run manually:
#   bench --site <site> execute erp_analysis.oauth_setup.ensure_oauth_client
#   bench --site <site> execute erp_analysis.patches.ensure_sales_dashboard_table.execute
after_install = "erp_analysis.install.after_install"
after_migrate = "erp_analysis.install.after_migrate"

doc_events = {
	"E Catalogue": {
		"after_save": "erp_analysis.erp_analysis.doctype.e_catalogue.e_catalogue.after_save",
	},
	"Delivery Note": {
		"before_validate": "erp_analysis.delivery_note_defaults.before_validate",
	},
}

app_init = [
	"erp_analysis.permissions.customer.apply_customer_360_permission_patch",
	"erp_analysis.permissions.strict_empty_links.apply_strict_empty_link_patch",
	"erp_analysis.integrations.zatca_mobile_defer.apply_zatca_mobile_defer_patch",
]

before_request = [
	"erp_analysis.permissions.strict_empty_links.ensure_strict_empty_link_patch",
]

doctype_js = {
	"Payment Entry": "public/js/payment_entry.js",
	"Delivery Note": "public/js/delivery_note.js",
}

override_whitelisted_methods = {
	"frappe.client.get_list": "erp_analysis.permissions.mobile_client.client_get_list",
	"frappe.client.get": "erp_analysis.permissions.mobile_client.client_get",
	"frappe.desk.reportview.get": "erp_analysis.permissions.mobile_client.reportview_get",
	"frappe.model.workflow.apply_workflow": "erp_analysis.approvals.apply_workflow_mobile",
}

permission_query_conditions = {
	"Mode of Payment": "erp_analysis.permissions.mode_of_payment.get_permission_query_conditions",
}

has_permission = {
	"Mode of Payment": "erp_analysis.permissions.mode_of_payment.has_permission",
}

# Uninstallation
# ------------
# before_uninstall = "erp_analysis.uninstall.before_uninstall"
# after_uninstall = "erp_analysis.uninstall.after_uninstall"

# Desk Notifications
# ------------------
# override_doctype_class = {}
# override_whitelisted_methods = {}

# Document Events
# ---------------
# doc_events = {}

# Scheduled Tasks
# ---------------
# scheduler_events = {}

# Testing
# -------
# before_tests = "erp_analysis.install.before_tests"

# Overriding Methods
# ------------------------------
# ignore_links_on_delete = []
