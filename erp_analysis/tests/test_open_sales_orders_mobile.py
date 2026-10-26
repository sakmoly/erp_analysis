"""Open Sales Orders KPI + drill (Sales Dashboard)."""

from __future__ import annotations

import unittest

import frappe

from erp_analysis.services.sales_open_orders_widget import _level1_row, _level2_row
from erp_analysis.services.sales_orders import get_open_so_summary


class TestOpenSalesOrdersMobile(unittest.TestCase):
	def test_level1_row_subtitle_customer_and_delivery(self):
		row = _level1_row(
			{
				"sales_order": "SO-1",
				"customer_name": "Acme Trading",
				"delivery_date": "2026-08-15",
				"pending_delivery_value": 1000,
			}
		)
		self.assertIn("Acme Trading", row["subtitle"])
		self.assertIn("2026-08-15", row["subtitle"])
		self.assertEqual(row["value"], 1000)

	def test_level2_row_item_and_delivery(self):
		row = _level2_row(
			"SO-1",
			{
				"item_code": "SKU-1",
				"item_name": "Label Roll",
				"delivery_date": "2026-09-01",
				"pending_qty": 4,
				"uom": "Roll",
				"pending_amount": 500,
			},
		)
		self.assertEqual(row["label"], "Label Roll")
		self.assertIn("2026-09-01", row["subtitle"])
		self.assertEqual(row["value"], 500)

	def test_open_so_summary_integer_count(self):
		company = frappe.defaults.get_user_default("Company")
		if not company:
			self.skipTest("No default company")
		summary = get_open_so_summary(user=frappe.session.user, company=company, filters=None)
		self.assertIn("open_so_count", summary)
		self.assertIn("date_scope", summary)
		self.assertIsInstance(summary["open_so_count"], int)
		self.assertGreaterEqual(summary["open_so_count"], 0)
