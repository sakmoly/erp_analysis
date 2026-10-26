# Copyright (c) 2026, ERP Analysis Contributors

import frappe
from frappe.tests.utils import FrappeTestCase

from erp_analysis.services.analytics_dimensions import (
	normalize_division_slice_filters,
	parse_logical_filters,
)


class TestDivisionSliceFilters(FrappeTestCase):
	def test_retail_slice_key_rewritten_to_division(self):
		user = frappe.session.user
		out = normalize_division_slice_filters(user, None, {"retail": ["Retail"]})
		self.assertEqual(out.get("division"), ["Retail"])
		self.assertNotIn("retail", out)

	def test_software_slice_key_rewritten(self):
		user = frappe.session.user
		out = normalize_division_slice_filters(user, None, {"software": ["Software"]})
		self.assertEqual(out.get("division"), ["Software"])

	def test_parse_logical_filters_drops_blank_values(self):
		out = parse_logical_filters({"division": [""], "territory": ["Jeddah"]})
		self.assertNotIn("division", out)
		self.assertEqual(out.get("territory"), ["Jeddah"])

	def test_coalesce_item_group_to_sub_group(self):
		from erp_analysis.services.analytics_sales import _coalesce_dashboard_filter_keys

		out = _coalesce_dashboard_filter_keys({"division": ["Retail"], "item_group": ["Retail Systems"]})
		self.assertEqual(out.get("sub_group"), ["Retail Systems"])

	def test_resolve_mobile_sub_group_labels(self):
		if not frappe.db.table_exists("SalesDashBoard"):
			self.skipTest("SalesDashBoard not installed")
		from erp_analysis.services.analytics_sales import _coalesce_dashboard_filter_keys

		ind = _coalesce_dashboard_filter_keys(
			{"division": ["Industrial"], "sub_group": ["Consumables"]}
		)
		self.assertIn("Industrial Consumables", ind.get("sub_group") or [])

		sw = _coalesce_dashboard_filter_keys(
			{"division": ["Software"], "sub_group": ["Service (SE)"]}
		)
		self.assertIn("Software Service", sw.get("sub_group") or [])

		inferred = _coalesce_dashboard_filter_keys({"sub_group": ["Industrial Consumables"]})
		self.assertEqual(inferred.get("division"), ["Industrial"])
