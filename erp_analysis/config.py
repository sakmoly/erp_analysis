import frappe

OAUTH_APP_NAME = "Printechs Mobile"
DEFAULT_REDIRECT = "erpnext://oauth"


@frappe.whitelist(allow_guest=True)
def get_client_id():
	"""Public helper so mobile can discover OAuth client_id."""
	client_id = frappe.db.get_value(
		"OAuth Client", {"app_name": OAUTH_APP_NAME}, "client_id"
	)
	if not client_id:
		# Fallback: any client with password-friendly redirect
		client_id = frappe.db.get_value(
			"OAuth Client", {"default_redirect_uri": DEFAULT_REDIRECT}, "client_id"
		)
	return {"client_id": client_id}
