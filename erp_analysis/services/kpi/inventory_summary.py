"""Inventory summary KPIs for executive dashboard."""

from __future__ import annotations

from typing import Any, Optional

import frappe

from erp_analysis.permissions.access_profile import resolve_warehouse_scope, warehouse_sql


def get_inventory_summary_kpis(company: Optional[str] = None) -> dict[str, Any]:
	company = company or frappe.defaults.get_user_default("Company")
	if not company:
		return {"value": 0, "low_stock_count": 0, "non_moving_count": 0}

	wh_scope = resolve_warehouse_scope(company=company)
	wh_sql, wh_params = warehouse_sql(wh_scope, field="b.warehouse")

	value = float(
		frappe.db.sql(
			f"""
			SELECT COALESCE(SUM(b.actual_qty * COALESCE(b.valuation_rate, 0)), 0)
			FROM `tabBin` b
			INNER JOIN `tabWarehouse` w ON w.name = b.warehouse
			WHERE w.company = %s
			  {wh_sql}
			""",
			tuple([company] + wh_params),
		)[0][0]
		or 0
	)

	low_stock_count = int(
		frappe.db.sql(
			f"""
			SELECT COUNT(DISTINCT b.item_code)
			FROM `tabBin` b
			INNER JOIN `tabWarehouse` w ON w.name = b.warehouse
			INNER JOIN `tabItem Reorder` ir
				ON ir.parent = b.item_code AND ir.warehouse = b.warehouse
			WHERE w.company = %s
			  AND b.actual_qty > 0
			  AND ir.warehouse_reorder_level > 0
			  AND b.actual_qty <= ir.warehouse_reorder_level
			  {wh_sql}
			""",
			tuple([company] + wh_params),
		)[0][0]
		or 0
	)

	sle_wh_sql, sle_wh_params = warehouse_sql(wh_scope, field="warehouse")
	non_moving_count = int(
		frappe.db.sql(
			f"""
			SELECT COUNT(*) FROM (
				SELECT b.item_code, b.warehouse
				FROM `tabBin` b
				INNER JOIN `tabWarehouse` w ON w.name = b.warehouse
				LEFT JOIN (
					SELECT item_code, warehouse, MAX(posting_date) AS last_movement
					FROM `tabStock Ledger Entry`
					WHERE company = %s AND is_cancelled = 0
					  {sle_wh_sql}
					GROUP BY item_code, warehouse
				) lm ON lm.item_code = b.item_code AND lm.warehouse = b.warehouse
				WHERE w.company = %s
				  AND b.actual_qty > 0
				  AND DATEDIFF(CURDATE(), COALESCE(lm.last_movement, CURDATE())) > 30
				  {wh_sql}
				GROUP BY b.item_code, b.warehouse
			) t
			""",
			tuple([company] + sle_wh_params + [company] + wh_params),
		)[0][0]
		or 0
	)

	return {
		"value": round(value, 2),
		"low_stock_count": low_stock_count,
		"non_moving_count": non_moving_count,
	}
