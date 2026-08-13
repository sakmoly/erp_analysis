# Copyright (c) 2026, ERP Analysis Contributors

import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import patch


class TestMobileWidgetsExtended(FrappeTestCase):
	def test_link_widget_returns_navigation_action(self):
		from erp_analysis.services.mobile_widgets import get_dashboard_widget_data

		widget = {
			"key": "goto_receivables",
			"label": "Receivables",
			"widget_type": "LINK",
			"module_key": "receivables",
			"config": {
				"action": {
					"type": "navigate",
					"target": "dashboard",
					"dashboard_id": "receivables_home",
				}
			},
		}
		with patch(
			"erp_analysis.services.mobile_widgets.resolve_widget_definition",
			return_value=widget,
		), patch(
			"erp_analysis.services.mobile_widgets.guard_mobile_api",
			return_value={"user": frappe.session.user, "company": None},
		):
			result = get_dashboard_widget_data(user=frappe.session.user, widget_key="goto_receivables")

		self.assertEqual(result["widget_type"], "LINK")
		self.assertEqual(result["action"]["dashboard_id"], "receivables_home")

	def test_chart_compare_ly_in_series(self):
		from erp_analysis.services.mobile_widgets import get_dashboard_widget_data

		widget = {
			"key": "sales_card",
			"label": "Sales",
			"widget_type": "BAR",
			"module_key": "sales",
			"metric_key": "net_sales",
			"dimension_key": "territory",
			"config": {"compare": "ly"},
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
						"label": "Jeddah",
						"dimension_value": "Jeddah",
						"metric_value": 100.0,
						"metric_value_ly": 80.0,
						"change_pct": 25.0,
					}
				],
				"meta": {"compare": "ly", "filters": {}, "schema_version": 1},
			},
		):
			result = get_dashboard_widget_data(user=frappe.session.user, widget_key="sales_card")

		point = result["chart"]["series"][0]
		self.assertEqual(result["chart"]["compare"], "ly")
		self.assertEqual(point["value_ly"], 80.0)
		self.assertEqual(point["change_pct"], 25.0)


class TestMobileDashboardBoards(FrappeTestCase):
	PROFILE_PREFIX = "__TEST_DASHBOARDS__"

	def tearDown(self):
		for name in frappe.get_all(
			"Mobile App Profile", pluck="name", filters={"name": ["like", f"{self.PROFILE_PREFIX}%"]}
		):
			frappe.delete_doc("Mobile App Profile", name, force=1, ignore_permissions=True)
		super().tearDown()

	def test_profile_dashboard_boards_group_widgets(self):
		from erp_analysis.services.mobile_profile import get_profile_dashboard_boards

		doc = frappe.get_doc(
			{
				"doctype": "Mobile App Profile",
				"profile_name": f"{self.PROFILE_PREFIX}-BOARDS",
				"business_type": "B2B",
				"enabled": 1,
				"default_dashboard": "home",
				"dashboards": [
					{"dashboard_key": "home", "label": "Home", "enabled": 1, "sort_order": 0},
					{"dashboard_key": "receivables_home", "label": "Receivables", "enabled": 1, "sort_order": 1},
				],
				"dashboard_widgets": [
					{
						"widget_key": "sales_card",
						"label": "Sales",
						"widget_type": "PIE",
						"dashboard_id": "home",
						"enabled": 1,
					},
					{
						"widget_key": "receivables_card",
						"label": "Receivables",
						"widget_type": "LIST",
						"dashboard_id": "receivables_home",
						"enabled": 1,
					},
				],
			}
		)
		doc.insert(ignore_permissions=True)

		boards = get_profile_dashboard_boards(doc.name)
		self.assertEqual(len(boards), 2)
		self.assertEqual(boards[0]["key"], "home")
		self.assertEqual(len(boards[0]["widgets"]), 1)
		self.assertEqual(boards[1]["widgets"][0]["key"], "receivables_card")

	def test_bootstrap_includes_dashboard_boards(self):
		from erp_analysis.services.mobile_bootstrap import build_mobile_bootstrap

		doc_name = f"{self.PROFILE_PREFIX}-BOOT"
		doc = frappe.get_doc(
			{
				"doctype": "Mobile App Profile",
				"profile_name": doc_name,
				"business_type": "B2B",
				"enabled": 1,
				"default_dashboard": "home",
				"dashboards": [{"dashboard_key": "home", "label": "Home", "enabled": 1}],
				"dashboard_widgets": [
					{"widget_key": "sales_card", "widget_type": "PIE", "dashboard_id": "home", "enabled": 1}
				],
			}
		)
		doc.insert(ignore_permissions=True)

		with patch(
			"erp_analysis.services.mobile_bootstrap.resolve_mobile_app_profile_name",
			return_value=doc.name,
		):
			payload = build_mobile_bootstrap(user=frappe.session.user)

		self.assertIn("dashboards", payload)
		self.assertEqual(payload["dashboards"][0]["key"], "home")
		self.assertEqual(payload["dashboard"][0]["key"], "sales_card")
