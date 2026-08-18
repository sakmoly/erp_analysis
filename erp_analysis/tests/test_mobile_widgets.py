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

	def test_kpi_widget_returns_scalar_payload(self):
		from erp_analysis.services.mobile_widgets import get_dashboard_widget_data

		widget = {
			"key": "sales_dash_net_ytd_kpi",
			"label": "Net Sales",
			"widget_type": "KPI",
			"module_key": "sales",
			"metric_key": "net_sales",
			"period": "ytd",
			"show_ly": True,
			"config": {"compare": "ly", "format": "currency_compact"},
		}
		with patch(
			"erp_analysis.services.mobile_widgets.resolve_widget_definition",
			return_value=widget,
		), patch(
			"erp_analysis.services.mobile_widgets.guard_mobile_api",
			return_value={"user": frappe.session.user, "company": "Test Co"},
		), patch(
			"erp_analysis.services.analytics_sales.get_sales_kpi",
			return_value={
				"value": 1000.0,
				"value_ly": 800.0,
				"change_pct": 25.0,
				"direction": "up",
				"label": "Net Sales",
				"meta": {"period": "ytd", "compare": "ly"},
			},
		):
			result = get_dashboard_widget_data(
				user=frappe.session.user,
				widget_key="sales_dash_net_ytd_kpi",
			)

		self.assertEqual(result["widget_type"], "KPI")
		self.assertIn("kpi", result)
		self.assertEqual(result["kpi"]["value"], 1000.0)
		self.assertEqual(result["kpi"]["value_ly"], 800.0)
		self.assertEqual(result["kpi"]["change_pct"], 25.0)
		self.assertEqual(result["kpi"]["format"], "currency_compact")

	def test_table_widget_returns_rows_and_columns(self):
		from erp_analysis.services.mobile_widgets import get_dashboard_widget_data

		columns = [{"key": "dimension", "label": "Brand"}, {"key": "metric", "label": "Sales"}]
		widget = {
			"key": "sales_dash_by_brand",
			"label": "Sales by Brand",
			"widget_type": "TABLE",
			"module_key": "sales",
			"metric_key": "net_sales",
			"dimension_key": "brand",
			"period": "ytd",
			"table_columns_json": frappe.as_json(columns),
			"config": {"compare": "ly"},
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
				"data": [
					{
						"label": "NIKE",
						"dimension_value": "NIKE",
						"metric_value": 500.0,
						"metric_value_ly": 400.0,
						"change_pct": 25.0,
						"rank": 1,
					}
				],
				"meta": {"period": "ytd", "filters": {}},
			},
		):
			result = get_dashboard_widget_data(
				user=frappe.session.user,
				widget_key="sales_dash_by_brand",
				limit=5,
			)

		self.assertEqual(result["widget_type"], "TABLE")
		self.assertIn("table", result)
		self.assertEqual(len(result["table"]["rows"]), 1)
		self.assertEqual(result["table"]["rows"][0]["dimension"], "NIKE")
		self.assertEqual(result["table"]["columns"][0]["key"], "dimension")

	def test_drill_views_render_table_at_depth(self):
		from erp_analysis.services.mobile_widgets import get_dashboard_widget_data

		widget = {
			"key": "sales_dash_territory",
			"label": "Sales by Territory",
			"widget_type": "DONUT",
			"module_key": "sales",
			"metric_key": "net_sales",
			"dimension_key": "territory",
			"period": "ytd",
			"config": {
				"drill_path": ["territory", "brand"],
				"drill_views": {"0": "donut", "1": "table"},
			},
		}
		with patch(
			"erp_analysis.services.mobile_widgets.resolve_widget_definition",
			return_value=widget,
		), patch(
			"erp_analysis.services.mobile_widgets.guard_mobile_api",
			return_value={"user": frappe.session.user, "company": None},
		), patch(
			"erp_analysis.services.analytics_sales.get_sales_analysis",
			return_value={"data": [], "meta": {"filters": {}}},
		):
			result = get_dashboard_widget_data(
				user=frappe.session.user,
				widget_key="sales_dash_territory",
				drill_depth=1,
			)

		self.assertIn("table", result)
		self.assertEqual(result["meta"]["render_hint"], "table")

	def test_batch_board_data_endpoint_whitelisted(self):
		method = frappe.get_attr("erp_analysis.api.get_dashboard_board_data")
		self.assertFalse(getattr(method, "allow_guest", False))

	def test_batch_board_data_accepts_null_use_cache(self):
		from erp_analysis.services.mobile_widgets import get_dashboard_board_data

		with patch(
			"erp_analysis.services.mobile_widgets.resolve_mobile_app_profile_name",
			return_value="PRINTECHS-B2B",
		), patch(
			"erp_analysis.services.mobile_widgets.get_profile_widgets",
			return_value=[
				{
					"key": "sales_dash_net_ytd_kpi",
					"widget_type": "KPI",
					"module_key": "sales",
					"config": {},
				}
			],
		), patch(
			"erp_analysis.services.mobile_widgets.guard_mobile_api",
			return_value={"user": frappe.session.user, "company": "Test Co"},
		), patch(
			"erp_analysis.api._get_my_access",
			return_value={"scope": {"company": "Test Co"}},
		), patch(
			"erp_analysis.services.mobile_widgets._build_widget_payload",
			return_value={"widget_key": "sales_dash_net_ytd_kpi", "widget_type": "KPI"},
		):
			result = get_dashboard_board_data(
				user=frappe.session.user,
				dashboard_id="sales_overview",
				use_cache=None,
				refresh=None,
			)

		self.assertEqual(result["dashboard_id"], "sales_overview")

	def test_batch_board_data_loads_widgets(self):
		from erp_analysis.services.mobile_widgets import get_dashboard_board_data

		widgets = [
			{
				"key": "sales_dash_net_ytd_kpi",
				"label": "Net Sales",
				"widget_type": "KPI",
				"module_key": "sales",
				"metric_key": "net_sales",
				"period": "ytd",
				"show_ly": True,
				"config": {},
			}
		]
		with patch(
			"erp_analysis.services.mobile_widgets.resolve_mobile_app_profile_name",
			return_value="PRINTECHS-B2B",
		), patch(
			"erp_analysis.services.mobile_widgets.get_profile_widgets",
			return_value=widgets,
		), patch(
			"erp_analysis.services.mobile_widgets.guard_mobile_api",
			return_value={"user": frappe.session.user, "company": "Test Co"},
		), patch(
			"erp_analysis.api._get_my_access",
			return_value={"scope": {"company": "Test Co"}},
		), patch(
			"erp_analysis.services.mobile_widgets._build_widget_payload",
			return_value={"widget_key": "sales_dash_net_ytd_kpi", "widget_type": "KPI", "kpi": {"value": 1}},
		):
			result = get_dashboard_board_data(
				user=frappe.session.user,
				dashboard_id="sales_overview",
				use_cache=False,
			)

		self.assertEqual(result["dashboard_id"], "sales_overview")
		self.assertIn("sales_dash_net_ytd_kpi", result["widgets"])
