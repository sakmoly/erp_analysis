# Copyright (c) 2026, ERP Analysis Contributors

import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import patch


class TestHomeNetProfit(FrappeTestCase):
	def test_net_profit_is_gl_income_minus_expense(self):
		from erp_analysis.services.kpi.home_metrics import _net_profit_kpi

		with patch(
			"erp_analysis.services.kpi.home_metrics._gl_net_profit_total",
			return_value=3_599_383.48,
		):
			result = _net_profit_kpi(
				company="Test Co",
				period="ytd",
				from_date=None,
				to_date=None,
			)

		self.assertEqual(result["value"], 3_599_383.48)
		self.assertEqual(result["metric"], "net_profit")
