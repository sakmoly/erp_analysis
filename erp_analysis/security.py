"""Central authentication guards for erp_analysis mobile/analytics APIs."""

from __future__ import annotations

import frappe
from frappe import _


def require_authenticated_user() -> str:
	"""Raise if the current session is not a logged-in user."""
	user = frappe.session.user
	if not user or user == "Guest":
		frappe.throw(_("Authentication required"), frappe.AuthenticationError)
	return user
