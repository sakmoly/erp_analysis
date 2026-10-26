"""Customer advances (unallocated PE) service tests."""

from __future__ import annotations

import unittest

import frappe

from erp_analysis.services.collection import get_customer_advances_summary


class TestCustomerAdvances(unittest.TestCase):
	def test_summary_returns_schema(self):
		company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value(
			"Global Defaults", "default_company"
		)
		if not company:
			self.skipTest("No default company")
		out = get_customer_advances_summary(company=company)
		self.assertIn("total_advance", out)
		self.assertIn("customer_count", out)
		self.assertIn("payment_count", out)
		self.assertGreaterEqual(out["total_advance"], 0)
