# Copyright (c) 2026, ERP Analysis Contributors

import frappe
from frappe.tests.utils import FrappeTestCase

from erp_analysis.services.payables import get_open_payables_invoices, get_payables_dashboard_payload


class TestPayablesInvoices(FrappeTestCase):
	def test_open_invoices_filtered_by_supplier(self):
		rows = get_open_payables_invoices(
			frappe.defaults.get_user_default("Company"),
			supplier="Westcon Saudi Company",
			limit=10,
		)
		if not rows:
			self.skipTest("No open Westcon purchase invoices on this site")
		self.assertLessEqual(len(rows), 10)
		for row in rows:
			self.assertEqual(row["supplier"], "Westcon Saudi Company")
			self.assertGreater(float(row["outstanding"]), 0)
			self.assertIn("invoice", row)

	def test_dashboard_payload_includes_invoices_when_supplier_set(self):
		payload = get_payables_dashboard_payload(
			frappe.defaults.get_user_default("Company"),
			supplier="Westcon Saudi Company",
			include_invoices=True,
			invoice_limit=100,
		)
		self.assertIn("invoices", payload)
		self.assertIn("open_invoices", payload)
		self.assertEqual(len(payload["invoices"]), len(payload["open_invoices"]))
