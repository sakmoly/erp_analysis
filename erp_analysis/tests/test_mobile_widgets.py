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

	def test_drill_depth_overrides_stale_dimension_param(self):
		from erp_analysis.services.mobile_widgets import get_dashboard_widget_data

		widget = {
			"key": "sales_by_division",
			"label": "Sales By Division",
			"widget_type": "RANKING",
			"module_key": "sales",
			"metric_key": "net_sales",
			"dimension_key": "division",
			"config": {"drill_path": ["division", "sub_group", "brand"]},
		}
		with patch(
			"erp_analysis.services.mobile_widgets.resolve_widget_definition",
			return_value=widget,
		), patch(
			"erp_analysis.services.mobile_widgets.guard_mobile_api",
			return_value={"user": frappe.session.user, "company": "Test Co"},
		), patch(
			"erp_analysis.services.analytics_sales.get_sales_analysis",
			return_value={"data": [], "meta": {"filters": {}, "schema_version": 1}},
		) as mock_analysis:
			get_dashboard_widget_data(
				user=frappe.session.user,
				widget_key="sales_by_division",
				dimension="sub_group",
				drill_depth=2,
				filters={"division": ["Industrial"], "sub_group": ["Industrial Consumables"]},
			)

		self.assertEqual(mock_analysis.call_args.kwargs["dimension"], "brand")

	def test_brand_drill_without_sub_group_is_empty(self):
		from erp_analysis.services.mobile_widgets import get_dashboard_widget_data

		widget = {
			"key": "sales_by_division",
			"label": "Sales By Division",
			"widget_type": "RANKING",
			"module_key": "sales",
			"metric_key": "net_sales",
			"dimension_key": "division",
			"config": {"drill_path": ["division", "sub_group", "brand"]},
		}
		with patch(
			"erp_analysis.services.mobile_widgets.resolve_widget_definition",
			return_value=widget,
		), patch(
			"erp_analysis.services.mobile_widgets.guard_mobile_api",
			return_value={"user": frappe.session.user, "company": "Test Co"},
		), patch(
			"erp_analysis.services.analytics_sales.get_sales_analysis",
			return_value={"data": [{"label": "Hitachi", "dimension_value": "Hitachi", "metric_value": 9e6}],
			 "meta": {"filters": {"division": ["Industrial"]}, "schema_version": 1}},
		) as mock_analysis:
			result = get_dashboard_widget_data(
				user=frappe.session.user,
				widget_key="sales_by_division",
				dimension="brand",
				filters={"division": ["Industrial"]},
			)

		mock_analysis.assert_not_called()
		self.assertEqual(result["meta"].get("empty_state"), "missing_drill_filter")
		self.assertEqual(result["table"]["rows"], [])

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
			return_value={
				"data": [
					{
						"dimension_value": "NIKE",
						"label": "NIKE",
						"metric_value": 100.0,
						"rank": 1,
					}
				],
				"meta": {"filters": {"territory": ["Jeddah"]}, "dimension": "brand"},
			},
		):
			result = get_dashboard_widget_data(
				user=frappe.session.user,
				widget_key="sales_dash_territory",
				drill_depth=1,
			)

		self.assertIn("table", result)
		self.assertEqual(result["meta"]["render_hint"], "table")
		self.assertIn("chart", result)
		self.assertEqual(len(result["chart"]["series"]), 1)
		self.assertEqual(result["chart"]["series"][0]["label"], "NIKE")

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

	def test_receivables_card_returns_territory_kpis_and_series(self):
		from erp_analysis.services.mobile_widgets import get_dashboard_widget_data

		widget = {
			"key": "receivables_card",
			"label": "Receivables Card",
			"widget_type": "PIE",
			"module_key": "receivables",
			"metric_key": "outstanding",
			"dimension_key": "territory",
			"legacy_method": "erp_analysis.receivables.get_receivables_dashboard",
			"config": {
				"payload_source": "legacy_chart",
				"rows_key": "territory_totals",
				"label_field": "territory",
				"value_field": "outstanding",
				"row_group": "receivables_card",
			},
		}
		legacy_payload = {
			"territory_totals": [
				{"territory": "Riyadh", "outstanding": 100.0},
				{"territory": "Jeddah", "outstanding": 200.0},
				{"territory": "Jeddah", "outstanding": 50.0},
			]
		}
		with patch(
			"erp_analysis.services.mobile_widgets.resolve_widget_definition",
			return_value=widget,
		), patch(
			"erp_analysis.services.mobile_widgets.guard_mobile_api",
			return_value={"user": frappe.session.user, "company": "Test Co"},
		), patch(
			"erp_analysis.services.mobile_widgets._call_legacy_method",
			return_value=legacy_payload,
		):
			result = get_dashboard_widget_data(
				user=frappe.session.user,
				widget_key="receivables_card",
			)

		self.assertEqual(result["widget_key"], "receivables_card")
		self.assertEqual(len(result["series"]), 2)
		self.assertEqual(len(result["kpis"]), 2)
		labels = {k["label"] for k in result["kpis"]}
		self.assertEqual(labels, {"Riyadh", "Jeddah"})
		jeddah = next(k for k in result["kpis"] if k["label"] == "Jeddah")
		self.assertEqual(jeddah["kpi_id"], "Jeddah")
		self.assertEqual(jeddah["value"], 200.0)
		self.assertEqual(jeddah["row_group"], "receivables_card")

	def test_sales_cogs_kpi_uses_gross_profit_engine(self):
		from erp_analysis.services.analytics_sales import get_sales_kpi

		with patch(
			"erp_analysis.services.analytics_sales._query_cogs_kpi",
			side_effect=[12823395.87, 15200000.0],
		):
			result = get_sales_kpi(
				user=frappe.session.user,
				company="Test Co",
				metric="cogs",
				period="ytd",
				compare="ly",
			)

		self.assertEqual(result["metric"], "cogs")
		self.assertEqual(result["label"], "COGS")
		self.assertEqual(result["value"], 12823395.87)
		self.assertEqual(result["value_ly"], 15200000.0)
		self.assertEqual(result["meta"]["format"], "currency_compact")

	def test_inventory_overview_kpis_use_distinct_module_metrics(self):
		from erp_analysis.services.mobile_widgets import _kpi_widget_payload

		mock_kpis = {
			"value": 15865556.33,
			"stock_qty": 2450000,
			"available_value": 12000000,
			"reserved_value": 3870000,
			"turnover": 4.2,
			"days_of_inventory": 68,
			"low_stock_count": 12,
			"non_moving_count": 34,
		}
		widgets = [
			("inventory_total_value_kpi", "inventory_value", "currency_compact"),
			("inventory_stock_qty_kpi", "stock_qty", "integer"),
			("inventory_available_value_kpi", "available_value", "currency_compact"),
			("inventory_reserved_value_kpi", "reserved_value", "currency_compact"),
			("inventory_turnover_kpi", "turnover", "decimal"),
			("inventory_days_kpi", "days_of_inventory", "integer"),
		]
		with patch(
			"erp_analysis.services.module_kpis.get_inventory_summary_kpis",
			return_value=mock_kpis,
		), patch(
			"erp_analysis.services.stock_cover.get_stock_cover_payload",
			return_value={"kpis": {"avg_cover_days": 68}},
		):
			for key, metric, fmt in widgets:
				payload = _kpi_widget_payload(
					frappe.session.user,
					"Printechs Advanced Printing Trading Co.",
					{
						"key": key,
						"label": key,
						"widget_type": "KPI",
						"module_key": "inventory",
						"metric_key": metric,
						"config": {"format": fmt},
					},
					None,
					None,
				)
				kpi = payload["kpi"]
				self.assertEqual(kpi["metric"], metric, key)
				self.assertIsNone(kpi.get("value_ly"), key)
				self.assertEqual(kpi["format"], fmt, key)
				if metric == "stock_qty":
					self.assertEqual(payload.get("stock_qty"), mock_kpis["stock_qty"])
				if metric == "available_value":
					self.assertEqual(payload.get("available_value"), mock_kpis["available_value"])

		values = {}
		with patch(
			"erp_analysis.services.module_kpis.get_inventory_summary_kpis",
			return_value=mock_kpis,
		), patch(
			"erp_analysis.services.stock_cover.get_stock_cover_payload",
			return_value={"kpis": {"avg_cover_days": 68}},
		):
			for key, metric, _fmt in widgets:
				payload = _kpi_widget_payload(
					frappe.session.user,
					"Printechs Advanced Printing Trading Co.",
					{
						"key": key,
						"widget_type": "KPI",
						"module_key": "inventory",
						"metric_key": metric,
						"config": {},
					},
					None,
					None,
				)
				values[key] = payload["kpi"]["value"]

		self.assertEqual(len(set(values.values())), len(values))
