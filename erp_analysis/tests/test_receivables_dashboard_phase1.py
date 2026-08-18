"""Receivables Phase 1 dashboard board tests."""

from __future__ import annotations

import unittest

import frappe

from erp_analysis.fixtures.operations_dashboard_widgets import RECEIVABLES_PHASE1_WIDGETS
from erp_analysis.services.module_kpis import get_module_kpi, is_module_kpi


class TestReceivablesDashboardPhase1(unittest.TestCase):
	def test_receivables_module_kpi_metrics(self):
		self.assertTrue(is_module_kpi("receivables", "total_receivable"))
		self.assertTrue(is_module_kpi("receivables", "overdue_pct"))
		self.assertTrue(is_module_kpi("receivables", "customer_count"))
		self.assertFalse(is_module_kpi("receivables", "net_sales"))

	def test_receivables_kpi_payload_shape(self):
		if not frappe.db.exists("Company", {"name": ("!=", "")}):
			self.skipTest("No company")
		company = frappe.db.get_value("Company", {}, "name")
		kpi = get_module_kpi(
			user="Administrator",
			company=company,
			module_key="receivables",
			metric_key="total_receivable",
		)
		self.assertIn("value", kpi)
		self.assertIn("meta", kpi)

	def test_phase1_widget_fixture_has_core_widgets(self):
		keys = {row["widget_key"] for row in RECEIVABLES_PHASE1_WIDGETS}
		for required in (
			"receivables_total_kpi",
			"receivables_aging_table",
			"receivables_overdue_customers_table",
		):
			self.assertIn(required, keys)

	def test_phase1_disabled_extra_charts(self):
		by_key = {row["widget_key"]: row for row in RECEIVABLES_PHASE1_WIDGETS}
		self.assertEqual(by_key["receivables_aging_donut"]["enabled"], 0)
		self.assertEqual(by_key["receivables_territory_table"]["enabled"], 0)
