# Copyright (c) 2026, ERP Analysis Contributors

import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import patch

from erp_analysis.access_context import get_effective_company
from erp_analysis.permissions.access_profile import resolve_territory_scope
from erp_analysis.services.analytics_dimensions import validate_logical_filters


class TestSecurityScope(FrappeTestCase):
	"""Phase I — scope tests use mocks; no live Access Profile / User changes."""

	def test_non_profile_user_no_territory_filter_by_default(self):
		with patch(
			"erp_analysis.permissions.access_profile._get_user_profile_name",
			return_value=None,
		):
			scope = resolve_territory_scope(company=None, purpose="view", module="sales")
		self.assertIsNone(scope)

	def test_non_profile_user_explicit_territory_filter_honored(self):
		with patch(
			"erp_analysis.permissions.access_profile._get_user_profile_name",
			return_value=None,
		):
			scope = resolve_territory_scope(requested="Riyadh", company=None, purpose="view", module="sales")
		self.assertEqual(scope, ["Riyadh"])

	def test_profile_user_out_of_scope_territory_rejected(self):
		with patch(
			"erp_analysis.permissions.access_profile._get_user_profile_name",
			return_value="TEST-AP-SCOPE",
		), patch(
			"erp_analysis.permissions.access_profile.get_view_territories",
			return_value=["Jeddah"],
		):
			with self.assertRaises(frappe.PermissionError):
				resolve_territory_scope(requested="Riyadh", company="Printechs Advanced Printing Trading Co.")

	def test_profile_user_in_scope_territory_allowed(self):
		with patch(
			"erp_analysis.permissions.access_profile._get_user_profile_name",
			return_value="TEST-AP-SCOPE",
		), patch(
			"erp_analysis.permissions.access_profile.get_view_territories",
			return_value=["Jeddah", "Riyadh"],
		):
			scope = resolve_territory_scope(requested="Jeddah", company="Printechs Advanced Printing Trading Co.")
		self.assertEqual(scope, ["Jeddah"])

	def test_territory_injection_via_analytics_filters_rejected(self):
		with patch(
			"erp_analysis.permissions.access_profile._get_user_profile_name",
			return_value="TEST-AP-SCOPE",
		), patch(
			"erp_analysis.permissions.access_profile.get_view_territories",
			return_value=["Jeddah"],
		), patch(
			"erp_analysis.services.analytics_dimensions.resolve_effective_dimension",
			return_value={
				"dimension_key": "territory",
				"allow_filter": 1,
				"source_doctype": "Sales Invoice",
				"source_field": "territory",
			},
		):
			with self.assertRaises(frappe.PermissionError):
				validate_logical_filters(
					frappe.session.user,
					"Printechs Advanced Printing Trading Co.",
					{"territory": ["Riyadh"]},
				)

	def test_non_profile_user_company_request_honored(self):
		company = get_effective_company(
			user=frappe.session.user,
			requested="Any Company Name",
			access={"scope": {}},
		)
		self.assertEqual(company, "Any Company Name")

	def test_profile_user_cross_company_rejected(self):
		with self.assertRaises(frappe.PermissionError):
			get_effective_company(
				user=frappe.session.user,
				requested="Other Company",
				access={"scope": {"company": "Printechs Advanced Printing Trading Co."}},
			)

	def test_view_all_sales_override_clears_territory_scope(self):
		with patch(
			"erp_analysis.permissions.access_profile._get_user_profile_name",
			return_value="TEST-AP-SCOPE",
		), patch(
			"erp_analysis.permissions.access_profile.get_view_territories",
			return_value=["Jeddah"],
		), patch(
			"erp_analysis.permissions.access_profile.bypass_view_territories",
			return_value=True,
		):
			scope = resolve_territory_scope(company="Printechs Advanced Printing Trading Co.", module="sales")
		self.assertIsNone(scope)

	def test_approve_scope_separate_from_view(self):
		with patch(
			"erp_analysis.permissions.access_profile._get_user_profile_name",
			return_value="TEST-AP-SCOPE",
		), patch(
			"erp_analysis.permissions.access_profile.get_approve_territories",
			return_value=["Dammam"],
		), patch(
			"erp_analysis.permissions.access_profile.get_view_territories",
			return_value=["Jeddah"],
		):
			view = resolve_territory_scope(purpose="view", company="Printechs Advanced Printing Trading Co.")
			approve = resolve_territory_scope(purpose="approve", company="Printechs Advanced Printing Trading Co.")
		self.assertEqual(view, ["Jeddah"])
		self.assertEqual(approve, ["Dammam"])
