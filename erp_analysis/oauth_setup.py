import frappe

APP_NAME = "Printechs Mobile"
DEFAULT_REDIRECT = "erpnext://oauth"
REDIRECT_URIS = "\n".join(
	[
		"erpnext://oauth",
		"erpnext://redirect",
		"exp://127.0.0.1:8081/--/oauth",
		"exp://localhost:8081/--/oauth",
		"https://printechs.com/mobile/oauth",
		"http://localhost:5173/mobile/oauth",
	]
)


@frappe.whitelist()
def ensure_oauth_client():
	"""
	Create/update OAuth Client for mobile password grant login.

	Frappe Desk Select options list Authorization Code / Implicit only, but the
	OAuth provider accepts grant_type=password at the token endpoint. We store
	grant_type as Authorization Code for Desk UI and rely on password support
	in frappe.oauth.OAuthWebRequestValidator.validate_grant_type.
	"""
	name = frappe.db.get_value("OAuth Client", {"app_name": APP_NAME}, "name")
	if name:
		doc = frappe.get_doc("OAuth Client", name)
	else:
		doc = frappe.new_doc("OAuth Client")
		doc.app_name = APP_NAME

	doc.default_redirect_uri = DEFAULT_REDIRECT
	doc.redirect_uris = REDIRECT_URIS
	doc.scopes = "all openid"
	# Keep a Desk-valid grant_type; password is still accepted by the provider.
	doc.grant_type = "Authorization Code"
	doc.response_type = "Code"
	doc.skip_authorization = 0

	if name:
		doc.save(ignore_permissions=True)
	else:
		doc.insert(ignore_permissions=True)

	frappe.db.commit()

	# Annotate for operators: password grant works with this client_id
	frappe.db.set_value(
		"OAuth Client",
		doc.name,
		{
			"default_redirect_uri": DEFAULT_REDIRECT,
			"redirect_uris": REDIRECT_URIS,
		},
		update_modified=False,
	)
	frappe.db.commit()

	return {
		"ok": True,
		"name": doc.name,
		"client_id": doc.client_id,
		"app_name": doc.app_name,
		"default_redirect_uri": doc.default_redirect_uri,
		"note": "Use grant_type=password with this client_id on /api/method/frappe.integrations.oauth2.get_token",
	}
