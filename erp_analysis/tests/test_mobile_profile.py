# Copyright (c) 2026, ERP Analysis Contributors

import frappe
from frappe.tests.utils import FrappeTestCase

from erp_analysis.services.mobile_dimensions import validate_dimension_definition
from erp_analysis.services.mobile_profile import resolve_mobile_app_profile_name


class TestMobileProfile(FrappeTestCase):
	def test_resolve_returns_none_without_profile_link(self):
		"""Users without a linked profile must fall back to legacy config (no profile)."""
		# Guest never resolves a profile
		self.assertIsNone(resolve_mobile_app_profile_name(user="Guest"))

	def test_validate_dimension_rejects_forbidden_doctype(self):
		class Row:
			source_mode = "FIELD"
			source_doctype = "User"
			source_field = "email"
			join_path_json = ""

		with self.assertRaises(frappe.ValidationError):
			validate_dimension_definition(Row())

	def test_validate_dimension_accepts_territory_on_customer(self):
		if not frappe.db.exists("DocType", "Customer"):
			self.skipTest("Customer DocType missing")

		class Row:
			source_mode = "FIELD"
			source_doctype = "Customer"
			source_field = "territory"
			join_path_json = ""

		validate_dimension_definition(Row())

	def test_mobile_app_profile_doctype_exists_after_migrate(self):
		self.assertTrue(frappe.db.exists("DocType", "Mobile App Profile"))
		self.assertTrue(frappe.db.exists("DocType", "Mobile App Module"))
		self.assertTrue(frappe.db.exists("DocType", "Mobile Analysis Dimension"))
		self.assertTrue(frappe.db.exists("DocType", "Mobile Dashboard Widget"))

	def test_access_profile_has_optional_mobile_link_field(self):
		meta = frappe.get_meta("Access Profile")
		self.assertTrue(meta.has_field("mobile_app_profile"))

	def test_mobile_app_settings_has_default_profile_field(self):
		meta = frappe.get_meta("Mobile App Settings")
		self.assertTrue(meta.has_field("default_mobile_app_profile"))
