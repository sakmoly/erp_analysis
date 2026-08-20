# Copyright (c) 2026, ERP Analysis Contributors

import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import patch


class TestHomeNetProfit(FrappeTestCase):
	def test_net_profit_is_gross_profit_minus_operating_expense(self):
		from erp_analysis.services.kpi.home_metrics import _net_profit_kpi

		with patch(
			"erp_analysis.services.kpi.home_metrics._gross_profit_kpi",
			return_value={"value": 3_360_115.78, "value_ly": None},
		), patch(
			"erp_analysis.services.kpi.home_metrics._gl_operating_expense_total",
			return_value=1_181_867.02,
		):
			result = _net_profit_kpi(
				company="Test Co",
				period="ytd",
				from_date=None,
				to_date=None,
			)

		self.assertEqual(result["value"], 2_178_248.76)
		self.assertLess(result["value"], 3_360_115.78)
