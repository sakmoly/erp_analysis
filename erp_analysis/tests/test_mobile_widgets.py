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
				"config": {},
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
				"config": {},
			},
		), patch(
			"erp_analysis.services.mobile_widgets.guard_mobile_api",
			return_value={"user": frappe.session.user, "company": None},
		):
			with self.assertRaises(frappe.ValidationError):
				get_dashboard_widget_data(user=frappe.session.user, widget_key="sales_card")

	def test_chart_drill_down_passes_filters_and_dimension(self):
		from erp_analysis.services.mobile_widgets import get_dashboard_widget_data

		widget = {
			"key": "sales_by_brand",
			"label": "Sales by Brand",
			"widget_type": "PIE",
			"module_key": "sales",
			"metric_key": "net_sales",
			"dimension_key": "brand",
			"config": {"drill_path": ["brand", "territory", "salesperson"]},
		}
		with patch(
			"erp_analysis.services.mobile_widgets.resolve_widget_definition",
			return_value=widget,
		), patch(
			"erp_analysis.services.mobile_widgets.guard_mobile_api",
			return_value={"user": frappe.session.user, "company": "Test Co"},
		), patch(
			"erp_analysis.services.analytics_sales.get_sales_analysis",
			return_value={
				"data": [{"label": "Jeddah", "dimension_value": "Jeddah", "metric_value": 100.0}],
				"meta": {"filters": {"brand": ["NIKE"]}, "schema_version": 1},
			},
		) as mock_analysis:
			result = get_dashboard_widget_data(
				user=frappe.session.user,
				widget_key="sales_by_brand",
				dimension="territory",
				filters='{"brand": ["NIKE"]}',
				limit=8,
			)

		mock_analysis.assert_called_once()
		call_kwargs = mock_analysis.call_args.kwargs
		self.assertEqual(call_kwargs["dimension"], "territory")
		self.assertEqual(call_kwargs["filters"], '{"brand": ["NIKE"]}')
		self.assertEqual(result["chart"]["dimension"], "territory")
		self.assertEqual(result["chart"]["filters"], {"brand": ["NIKE"]})
		self.assertEqual(result["meta"]["next_dimension"], "salesperson")
		self.assertTrue(result["meta"]["drillable"])

	def test_drill_depth_selects_dimension_from_config(self):
		from erp_analysis.services.mobile_widgets import get_dashboard_widget_data

		widget = {
			"key": "sales_by_brand",
			"label": "Sales by Brand",
			"widget_type": "BAR",
			"module_key": "sales",
			"metric_key": "net_sales",
			"dimension_key": "brand",
			"config": {"drill_path": ["brand", "territory"]},
		}
		with patch(
			"erp_analysis.services.mobile_widgets.resolve_widget_definition",
			return_value=widget,
		), patch(
			"erp_analysis.services.mobile_widgets.guard_mobile_api",
			return_value={"user": frappe.session.user, "company": None},
		), patch(
			"erp_analysis.services.analytics_sales.get_sales_analysis",
			return_value={"data": [], "meta": {"filters": {}, "schema_version": 1}},
		) as mock_analysis:
			result = get_dashboard_widget_data(
				user=frappe.session.user,
				widget_key="sales_by_brand",
				drill_depth=1,
				filters={"brand": ["ADIDAS"]},
			)

		self.assertEqual(mock_analysis.call_args.kwargs["dimension"], "territory")
		self.assertEqual(result["meta"]["drill_depth"], 1)
		self.assertIsNone(result["meta"]["next_dimension"])
		self.assertFalse(result["meta"]["drillable"])
