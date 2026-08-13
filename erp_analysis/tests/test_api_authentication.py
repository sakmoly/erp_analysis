# Copyright (c) 2026, ERP Analysis Contributors

import frappe
from frappe.tests.utils import FrappeTestCase


class TestApiAuthentication(FrappeTestCase):
	"""Phase A — guest must not call sensitive mobile analytics APIs."""

	def test_require_authenticated_user_rejects_guest(self):
		from erp_analysis.security import require_authenticated_user

		original = self.session.user
		try:
			self.session.user = "Guest"
			with self.assertRaises(frappe.AuthenticationError):
				require_authenticated_user()
		finally:
			self.session.user = original

	def test_require_authenticated_user_accepts_logged_in_user(self):
		from erp_analysis.security import require_authenticated_user

		user = require_authenticated_user()
		self.assertTrue(user)
		self.assertNotEqual(user, "Guest")

	def test_sensitive_endpoints_not_guest_whitelisted(self):
		import frappe

		guest_allowed = set()
		for method_path in (
			"erp_analysis.employee.get_employees",
			"erp_analysis.sales_kpis.get_dashboard_kpis",
			"erp_analysis.sales_kpis.get_today_sales_kpis",
			"erp_analysis.catalogue.get_catalogue_flip_url",
		):
			method = frappe.get_attr(method_path)
			if getattr(method, "allow_guest", False):
				guest_allowed.add(method_path)

		self.assertEqual(guest_allowed, set(), f"Guest allowed on: {guest_allowed}")
