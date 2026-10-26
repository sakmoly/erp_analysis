# Copyright (c) 2026, ERP Analysis Contributors

import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import patch


class TestSalesDrill(FrappeTestCase):
	def test_drill_normalizes_product_row_shape(self):
		from erp_analysis.services.sales_drill import get_sales_by_division_drill

		widget_payload = {
			"table": {
				"dimension": "brand",
				"filters": {"division": ["Industrial"], "sub_group": ["Industrial Systems"]},
				"rows": [
					{
						"dimension": "Hitachi",
						"dimension_value": "Hitachi",
						"metric": 1821214.93,
						"gross_profit": 900000.0,
						"gp_pct": 49.4,
						"rank": 1,
					}
				],
			},
			"meta": {
				"drill_depth": 2,
				"next_dimension": None,
				"drillable": False,
			},
		}
		with patch(
			"erp_analysis.services.mobile_widgets.get_dashboard_widget_data",
			return_value=widget_payload,
		):
			result = get_sales_by_division_drill(
				user=frappe.session.user,
				company="Test Co",
				drill_depth=2,
				filters={"division": ["Industrial"], "sub_group": ["Industrial Systems"]},
			)

		self.assertEqual(result["data_source"], "SalesDashBoard")
		row = result["rows"][0]
		self.assertEqual(row["total_sales"], 1821214.93)
		self.assertEqual(row["metric"], 1821214.93)
		self.assertEqual(row["dimension_value"], "Hitachi")

	def test_scoped_consumables_not_division_wide(self):
		from erp_analysis.services.sales_drill import assess_brand_drill_scope

		rows = [{"label": "Hitachi", "metric": 6_094_249.04}]
		with patch(
			"erp_analysis.services.sales_drill._dashboard_scalar",
			side_effect=[9_345_798.76, 9_086_380.55],
		):
			scope = assess_brand_drill_scope(
				company="Test Co",
				from_date=__import__("datetime").date(2026, 1, 1),
				to_date=__import__("datetime").date(2026, 10, 15),
				filters={"division": ["Industrial"], "sub_group": ["Industrial Consumables"]},
				rows=rows,
			)

		self.assertTrue(scope["accept_response"])
		self.assertEqual(scope["drill_scope_status"], "scoped")
		self.assertFalse(scope["is_division_wide_brand_mix"])
