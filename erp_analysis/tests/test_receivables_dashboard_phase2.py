"""Receivables Phase 2 dashboard board tests."""

from __future__ import annotations

import unittest

import frappe

from erp_analysis.fixtures.operations_dashboard_widgets import RECEIVABLES_PHASE2_WIDGETS
from erp_analysis.services.module_kpis import get_module_kpi, is_module_kpi


class TestReceivablesDashboardPhase2(unittest.TestCase):
	def test_phase2_module_kpi_metrics(self):
		self.assertTrue(is_module_kpi("receivables", "dso"))
		self.assertTrue(is_module_kpi("collection", "collection_efficiency"))
		self.assertTrue(is_module_kpi("collection", "avg_collection_days"))

	def test_phase2_widget_fixture_has_core_widgets(self):
		keys = {row["widget_key"] for row in RECEIVABLES_PHASE2_WIDGETS}
		for required in (
			"receivables_dso_kpi",
			"receivables_overdue_trend",
			"receivables_collected_mtd_kpi",
			"receivables_attention",
		):
			self.assertIn(required, keys)

	def test_dso_kpi_payload_shape(self):
		if not frappe.db.exists("Company", {"name": ("!=", "")}):
			self.skipTest("No company")
		company = frappe.db.get_value("Company", {}, "name")
		kpi = get_module_kpi(
			user="Administrator",
			company=company,
			module_key="receivables",
			metric_key="dso",
		)
		self.assertIn("value", kpi)
		self.assertGreaterEqual(float(kpi["value"]), 0)

	def test_overdue_trend_chart_api(self):
		from erp_analysis.receivables import get_receivables_overdue_trend_chart

		result = get_receivables_overdue_trend_chart()
		self.assertIn("series", result)
		self.assertIsInstance(result["series"], list)

	def test_attention_api(self):
		from erp_analysis.receivables import get_receivables_attention

		result = get_receivables_attention()
		self.assertIn("items", result)
		self.assertIsInstance(result["items"], list)
