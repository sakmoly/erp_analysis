# Copyright (c) 2026, ERP Analysis Contributors

import frappe
from frappe.tests.utils import FrappeTestCase


class TestApiAuthentication(FrappeTestCase):
	"""Phase A/I — guest must not call sensitive mobile analytics APIs."""

	_SENSITIVE_METHODS = (
		"erp_analysis.employee.get_employees",
		"erp_analysis.sales_kpis.get_dashboard_kpis",
		"erp_analysis.sales_kpis.get_today_sales_kpis",
		"erp_analysis.receivables.get_receivables_dashboard",
		"erp_analysis.payables.get_payables_dashboard",
		"erp_analysis.profitability.get_gross_profit_dashboard",
		"erp_analysis.collection.get_collection_dashboard",
		"erp_analysis.analytics.get_dimensions",
		"erp_analysis.api.get_mobile_bootstrap",
	)

	_PUBLIC_METHODS = (
		"erp_analysis.api.health",
		"erp_analysis.config.get_client_id",
	)

	def test_require_authenticated_user_rejects_guest(self):
		from erp_analysis.security import require_authenticated_user

		original = frappe.session.user
		try:
			frappe.set_user("Guest")
			with self.assertRaises(frappe.AuthenticationError):
				require_authenticated_user()
		finally:
			frappe.set_user(original)

	def test_require_authenticated_user_accepts_logged_in_user(self):
		from erp_analysis.security import require_authenticated_user

		user = require_authenticated_user()
		self.assertTrue(user)
		self.assertNotEqual(user, "Guest")

	def test_sensitive_endpoints_not_guest_whitelisted(self):
		guest_allowed = set()
		for method_path in self._SENSITIVE_METHODS:
			method = frappe.get_attr(method_path)
			if getattr(method, "allow_guest", False):
				guest_allowed.add(method_path)

		self.assertEqual(guest_allowed, set(), f"Guest allowed on: {guest_allowed}")

	def test_public_endpoints_allow_guest(self):
		import frappe

		for method_path in self._PUBLIC_METHODS:
			method = frappe.get_attr(method_path)
			fn = getattr(method, "__func__", method)
			self.assertIn(fn, frappe.guest_methods, method_path)
