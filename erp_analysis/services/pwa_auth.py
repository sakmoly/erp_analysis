"""PWA web login — issue OAuth bearer tokens without oauthlib password grant round-trip."""

from __future__ import annotations

import secrets

import frappe
from frappe.auth import LoginManager
from frappe.utils import add_to_date, now_datetime

from erp_analysis.oauth_setup import APP_NAME as OAUTH_APP_NAME

DEFAULT_EXPIRES_IN = 3600 * 24 * 7  # 7 days — align with typical mobile sessions


def issue_mobile_bearer_token(user: str, *, expires_in: int = DEFAULT_EXPIRES_IN) -> dict:
	client_name = frappe.db.get_value("OAuth Client", {"app_name": OAUTH_APP_NAME}, "name")
	if not client_name:
		frappe.throw("Printechs Mobile OAuth client is not configured")

	scopes = frappe.db.get_value("OAuth Client", client_name, "scopes") or "all openid"
	access_token = secrets.token_hex(20)
	refresh_token = secrets.token_hex(20)
	expiration_time = add_to_date(now_datetime(), seconds=expires_in, as_datetime=True)

	doc = frappe.get_doc(
		{
			"doctype": "OAuth Bearer Token",
			"client": client_name,
			"user": user,
			"scopes": scopes,
			"access_token": access_token,
			"refresh_token": refresh_token,
			"expires_in": expires_in,
			"expiration_time": expiration_time,
			"status": "Active",
		}
	)
	doc.insert(ignore_permissions=True)
	frappe.db.commit()

	return {
		"access_token": access_token,
		"refresh_token": refresh_token,
		"expires_in": expires_in,
		"token_type": "Bearer",
		"scope": scopes,
	}


def pwa_password_login(usr: str, pwd: str) -> dict:
	usr = (usr or "").strip()
	pwd = pwd or ""
	if not usr or not pwd:
		frappe.throw(frappe._("Missing credentials"), frappe.AuthenticationError)

	login_manager = LoginManager()
	login_manager.authenticate(user=usr, pwd=pwd)
	if login_manager.user in (None, "", "Guest"):
		frappe.throw(frappe._("Invalid login credentials"), frappe.AuthenticationError)

	token = issue_mobile_bearer_token(login_manager.user)
	return {
		**token,
		"user": login_manager.user,
		"full_name": frappe.utils.get_fullname(login_manager.user),
	}
