# Copyright (c) 2026, ERP Analysis Contributors

import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import patch


class TestMobileWidgets(FrappeTestCase):
	def test_sales_card_pie_returns_chart_series(self):
		from erp_analysis.services.mobile_widgets import get_dashboard_widget_data

		with patch(
			"erp_analysis.services.mobile_widgets.resolve_widget_definition",
			return_value={
				"key": "sales_card",
				"label": "Sales Performance",
				"widget_type": "PIE",
				"module_key": "sales",
				"metric_key": "net_sales",
				"dimension_key": "territory",
			},
		), patch(
			"erp_analysis.services.mobile_widgets.guard_mobile_api",
			return_value={"user": frappe.session.user, "company": None},
		):
			result = get_dashboard_widget_data(user=frappe.session.user, widget_key="sales_card", limit=5)

		self.assertEqual(result["widget_key"], "sales_card")
		self.assertEqual(result["widget_type"], "PIE")
		self.assertIn("chart", result)
		self.assertIn("series", result["chart"])
		self.assertEqual(result["chart"]["metric"], "net_sales")
		self.assertEqual(result["chart"]["dimension"], "territory")

	def test_widget_data_endpoint_whitelisted(self):
		method = frappe.get_attr("erp_analysis.api.get_dashboard_widget_data")
		self.assertFalse(getattr(method, "allow_guest", False))

	def test_matrix_widget_rejected(self):
		from erp_analysis.services.mobile_widgets import get_dashboard_widget_data

		with patch(
			"erp_analysis.services.mobile_widgets.resolve_widget_definition",
			return_value={
				"key": "sales_card",
				"label": "Sales",
				"widget_type": "MATRIX",
				"module_key": "sales",
			},
		), patch(
			"erp_analysis.services.mobile_widgets.guard_mobile_api",
			return_value={"user": frappe.session.user, "company": None},
		):
			with self.assertRaises(frappe.ValidationError):
				get_dashboard_widget_data(user=frappe.session.user, widget_key="sales_card")
