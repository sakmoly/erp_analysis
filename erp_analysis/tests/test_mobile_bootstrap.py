# Copyright (c) 2026, ERP Analysis Contributors

import frappe
from frappe.tests.utils import FrappeTestCase

from erp_analysis.security import require_authenticated_user
from erp_analysis.services.mobile_bootstrap import BOOTSTRAP_SCHEMA_VERSION, build_mobile_bootstrap


class TestMobileBootstrap(FrappeTestCase):
	def test_guest_cannot_build_bootstrap(self):
		original = frappe.session.user
		try:
			frappe.set_user("Guest")
			with self.assertRaises(frappe.AuthenticationError):
				build_mobile_bootstrap()
		finally:
			frappe.set_user(original)

	def test_authenticated_bootstrap_shape(self):
		payload = build_mobile_bootstrap(user=frappe.session.user)
		self.assertEqual(payload["schema_version"], BOOTSTRAP_SCHEMA_VERSION)
		self.assertIn("user", payload)
		self.assertIn("modules", payload)
		self.assertIn("dimensions", payload)
		self.assertIn("permissions", payload)
		self.assertIn("capabilities", payload)
		self.assertIn("meta", payload)
		self.assertIsInstance(payload["modules"], list)
		self.assertIsInstance(payload["dimensions"], list)

	def test_bootstrap_modules_are_dicts_with_key(self):
		payload = build_mobile_bootstrap(user=frappe.session.user)
		for mod in payload["modules"]:
			self.assertIn("key", mod)
			self.assertIn("enabled", mod)

	def test_get_mobile_bootstrap_whitelisted(self):
		method = frappe.get_attr("erp_analysis.api.get_mobile_bootstrap")
		self.assertFalse(getattr(method, "allow_guest", False))

	def test_require_authenticated_user(self):
		user = require_authenticated_user()
		self.assertNotEqual(user, "Guest")
