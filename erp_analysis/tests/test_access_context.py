# Copyright (c) 2026, ERP Analysis Contributors

import frappe
from frappe.tests.utils import FrappeTestCase

from erp_analysis.access_context import (
	get_authenticated_access_context,
	get_effective_company,
	guard_mobile_api,
	is_module_enabled_in_profile,
	require_authenticated_user,
)


class TestAccessContext(FrappeTestCase):
	def test_get_effective_company_allows_default_without_profile(self):
		company = get_effective_company(user=frappe.session.user, requested=None, access={"scope": {}})
		self.assertTrue(company)

	def test_get_effective_company_rejects_cross_company_request(self):
		with self.assertRaises(frappe.PermissionError):
			get_effective_company(
				user=frappe.session.user,
				requested="Other Company Ltd",
				access={"scope": {"company": "Printechs Advanced Printing Trading Co."}},
			)

	def test_guard_mobile_api_returns_authenticated_context(self):
		ctx = guard_mobile_api(module_key=None)
		self.assertEqual(ctx["user"], frappe.session.user)
		self.assertIn("access", ctx)
		self.assertIn("view_territory_scope", ctx)

	def test_is_module_enabled_without_profile_link(self):
		self.assertTrue(is_module_enabled_in_profile("sales", user=frappe.session.user))

	def test_get_authenticated_access_context_includes_company(self):
		ctx = get_authenticated_access_context(user=frappe.session.user)
		self.assertEqual(ctx["user"], frappe.session.user)
		self.assertIn("company", ctx)
		self.assertIn("view_territories", ctx)
