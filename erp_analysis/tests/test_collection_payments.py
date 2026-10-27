# Copyright (c) 2026, ERP Analysis Contributors

import frappe
from frappe.tests.utils import FrappeTestCase

from erp_analysis.services.collection import (
	COLLECTION_AMOUNT_FORMAT,
	_assign_collection_branch_territory,
	_payment_matches_territory_drill,
	format_collection_amount,
	get_collection_by_mode_of_payment,
	get_collection_by_territory,
	get_collection_payments_payload,
)


class TestCollectionPayments(FrappeTestCase):
	def test_branch_territory_assignment(self):
		known = {"Jeddah", "Dammam", "Riyadh"}
		self.assertEqual(
			_assign_collection_branch_territory("Jeddah", "Cash Collection - Dammam", known),
			"Dammam",
		)
		self.assertEqual(
			_assign_collection_branch_territory("Jeddah", "Wire Transfer", known),
			"Jeddah",
		)

	def test_dammam_cash_matches_gl_when_data_present(self):
		company = frappe.defaults.get_user_default("Company")
		if not company:
			self.skipTest("No default company")
		mops = get_collection_by_mode_of_payment(
			company=company,
			from_date="2026-01-01",
			to_date="2026-10-26",
			territory="Dammam",
			limit=20,
			territories=None,
		)
		cash = next((r for r in mops if r.get("mode_of_payment") == "Cash Collection - Dammam"), None)
		if not cash:
			self.skipTest("No Cash Collection - Dammam in period")
		self.assertEqual(cash["collected"], 53921.35)
		self.assertEqual(cash["debit"], 127853.50)
		self.assertEqual(cash["credit"], 73932.15)
		self.assertEqual(cash["amount_basis"], "gl_net")

	def test_format_collection_amount_integer(self):
		text = format_collection_amount(125430.67, "SAR")
		self.assertNotIn("K", text)
		self.assertNotIn("M", text)
		self.assertNotIn(".", text.replace(",", ""))
		self.assertIn("125", text)

	def test_territory_drill_mop_branch_rules(self):
		known = {"Jeddah", "Dammam", "Riyadh"}
		ok, _ = _payment_matches_territory_drill(
			customer_territory="Jeddah",
			mode_of_payment="Cash Collection - Jeddah",
			drill_territory="Jeddah",
			known_territories=known,
		)
		self.assertTrue(ok)
		ok, reason = _payment_matches_territory_drill(
			customer_territory="Jeddah",
			mode_of_payment="Cash Collection - Dammam",
			drill_territory="Jeddah",
			known_territories=known,
		)
		self.assertFalse(ok)
		self.assertEqual(reason, "other_branch_mop")
		ok, _ = _payment_matches_territory_drill(
			customer_territory="Riyadh",
			mode_of_payment="Cheques received - Jeddah",
			drill_territory="Jeddah",
			known_territories=known,
		)
		self.assertTrue(ok)

	def test_territory_drill_shape(self):
		company = frappe.defaults.get_user_default("Company")
		payload = get_collection_payments_payload(
			company=company,
			from_date="2026-01-01",
			to_date="2026-10-26",
			period="ytd",
			breakdown_type="territory",
			breakdown_id="Jeddah",
			limit=5,
			territories=None,
		)
		self.assertIn("meta", payload)
		self.assertIn("summary", payload)
		self.assertIn("items", payload)
		self.assertEqual(payload["meta"]["breakdown_type"], "territory")
		self.assertEqual(payload["meta"]["breakdown_id"], "Jeddah")
		self.assertEqual(payload["summary"]["payment_count_in_response"], len(payload["items"]))
		self.assertGreaterEqual(payload["summary"]["payment_count"], len(payload["items"]))
		self.assertIn("totals_by_mode_of_payment", payload["summary"])
		self.assertIn("territory_drill_filter", payload["meta"])
		self.assertEqual(payload["meta"]["amount_format"], COLLECTION_AMOUNT_FORMAT)
		if payload["items"]:
			item = payload["items"][0]
			self.assertEqual(item["amount_format"], COLLECTION_AMOUNT_FORMAT)
			self.assertEqual(item["paid_amount_display"], format_collection_amount(item["paid_amount"]))
		for item in payload["items"]:
			self.assertIn("payment_entry", item)
			self.assertIn("allocated_invoices", item)
			self.assertGreaterEqual(float(item["paid_amount"]), 0)
			self.assertIn("mode_of_payment", item)
			self.assertIn("receipt_number", item)
			self.assertIn("reference_no", item)
			self.assertEqual(item["receipt_number"], item.get("receipt_no"))
