# Copyright (c) 2026, ERP Analysis Contributors

import frappe
from frappe.tests.utils import FrappeTestCase

from erp_analysis.services.analytics_dimensions import (
	list_effective_dimensions,
	parse_logical_filters,
	resolve_effective_dimension,
)


class TestAnalyticsPhaseD(FrappeTestCase):
	def test_get_dimensions_returns_list(self):
		dims = list_effective_dimensions(frappe.session.user)
		self.assertIsInstance(dims, list)
		for row in dims:
			self.assertIn("key", row)
			self.assertNotIn("source_field", row)

	def test_parse_logical_filters(self):
		parsed = parse_logical_filters('{"brand": ["A", "B"], "territory": "Jeddah"}')
		self.assertEqual(parsed["brand"], ["A", "B"])
		self.assertEqual(parsed["territory"], ["Jeddah"])

	def test_unknown_dimension_raises(self):
		with self.assertRaises(frappe.ValidationError):
			resolve_effective_dimension(frappe.session.user, None, "not_a_real_dimension_xyz")

	def test_analytics_endpoints_not_guest(self):
		for path in (
			"erp_analysis.analytics.get_dimensions",
			"erp_analysis.analytics.get_dimension_values",
			"erp_analysis.analytics.get_sales_analysis",
		):
			method = frappe.get_attr(path)
			self.assertFalse(getattr(method, "allow_guest", False))

	def test_sales_analysis_service_shape(self):
		from erp_analysis.services.analytics_sales import get_sales_analysis

		dims = list_effective_dimensions(frappe.session.user)
		if not dims:
			self.skipTest("No enabled dimensions on site")

		result = get_sales_analysis(
			user=frappe.session.user,
			dimension=dims[0]["key"],
			metric="net_sales",
			limit=5,
		)
		self.assertIn("data", result)
		self.assertIn("meta", result)
		self.assertEqual(result["meta"]["metric"], "net_sales")
