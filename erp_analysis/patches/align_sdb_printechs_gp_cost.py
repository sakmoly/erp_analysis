"""Repoint ViewSalesDashBoardFromSI to ViewSalesGrossProfit (Printechs GP cost)."""

from __future__ import annotations

import frappe

from erp_analysis.patches.setup_sales_dashboard_from_si import _create_view


def execute():
	_create_view()
	frappe.db.commit()
	return {"ok": True, "view": "ViewSalesDashBoardFromSI", "source": "ViewSalesGrossProfit"}
