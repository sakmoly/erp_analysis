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
			self.assertIn("supplier_invoice_no", row)
			self.assertIn("vendor_invoice_no", row)
			self.assertEqual(row["supplier_invoice_no"], row.get("bill_no"))

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

	def test_overdue_is_financial_not_status_only(self):
		rows = get_open_payables_invoices(
			frappe.defaults.get_user_default("Company"),
			supplier="Avery Berkel - International",
			limit=50,
		)
		if not rows:
			self.skipTest("No open Avery purchase invoices on this site")
		for row in rows:
			self.assertGreater(float(row["outstanding"]), 0)
			if row.get("payable_state") == "current":
				self.assertFalse(row["is_payable_overdue"])
				self.assertEqual(row["days_overdue"], 0)
				self.assertEqual(row["overdue_outstanding"], 0.0)
			if row.get("is_payable_overdue"):
				self.assertGreater(row["days_overdue"], 0)
				self.assertEqual(row["overdue_outstanding"], row["outstanding"])
		current = [r for r in rows if r.get("invoice") == "PI26-0466"]
		if current:
			self.assertEqual(current[0]["payable_state"], "current")
			self.assertFalse(current[0]["is_payable_overdue"])
