"""Inventory summary KPIs for executive dashboard and mobile inventory boards."""

from __future__ import annotations

from typing import Any, Optional

import frappe

from erp_analysis.permissions.access_profile import resolve_warehouse_scope, warehouse_sql


def get_inventory_summary_kpis(company: Optional[str] = None) -> dict[str, Any]:
	company = company or frappe.defaults.get_user_default("Company")
	empty = {
		"value": 0,
		"stock_qty": 0,
		"available_value": 0,
		"reserved_value": 0,
		"turnover": 0,
		"days_of_inventory": 0,
		"low_stock_count": 0,
		"non_moving_count": 0,
	}
	if not company:
		return empty

	wh_scope = resolve_warehouse_scope(company=company)
	wh_sql, wh_params = warehouse_sql(wh_scope, field="b.warehouse")
	sle_wh_sql, sle_wh_params = warehouse_sql(wh_scope, field="s.warehouse")
	sle2_wh_sql, sle2_wh_params = warehouse_sql(wh_scope, field="sle.warehouse")

	bin_row = frappe.db.sql(
		f"""
		SELECT
			COALESCE(SUM(b.actual_qty), 0) AS stock_qty,
			COALESCE(SUM(b.actual_qty * COALESCE(b.valuation_rate, 0)), 0) AS value,
			COALESCE(SUM(b.reserved_qty * COALESCE(b.valuation_rate, 0)), 0) AS reserved_value,
			COALESCE(
				SUM(GREATEST(b.actual_qty - b.reserved_qty, 0) * COALESCE(b.valuation_rate, 0)),
				0
			) AS available_value
		FROM `tabBin` b
		INNER JOIN `tabWarehouse` w ON w.name = b.warehouse
		WHERE w.company = %s
		  {wh_sql}
		""",
		tuple([company] + wh_params),
		as_dict=True,
	)[0]

	value = float(bin_row.value or 0)
	stock_qty = float(bin_row.stock_qty or 0)
	reserved_value = float(bin_row.reserved_value or 0)
	available_value = float(bin_row.available_value or 0)

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

	non_moving_count = int(
		frappe.db.sql(
			f"""
			SELECT COUNT(*) FROM (
				SELECT b.item_code, b.warehouse
				FROM `tabBin` b
				INNER JOIN `tabWarehouse` w ON w.name = b.warehouse
				LEFT JOIN (
					SELECT s.item_code, s.warehouse, MAX(s.posting_date) AS last_movement
					FROM `tabStock Ledger Entry` s
					WHERE s.company = %s AND s.is_cancelled = 0
					  {sle_wh_sql}
					GROUP BY s.item_code, s.warehouse
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

	cogs_row = frappe.db.sql(
		f"""
		SELECT
			COALESCE(SUM(CASE WHEN s.actual_qty < 0 THEN ABS(s.stock_value_difference) ELSE 0 END), 0) AS cogs_12m,
			COALESCE(SUM(s.stock_value_difference), 0) AS net_change_12m
		FROM `tabStock Ledger Entry` s
		INNER JOIN `tabWarehouse` w ON w.name = s.warehouse
		WHERE w.company = %s
		  AND s.posting_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
		  {sle_wh_sql}
		""",
		tuple([company] + sle_wh_params),
		as_dict=True,
	)[0]
	cogs_12m = float(cogs_row.cogs_12m or 0)
	net_change_12m = float(cogs_row.net_change_12m or 0)
	opening_value = max(value - net_change_12m, 0.0)
	avg_inventory = (opening_value + value) / 2.0
	turnover = round(cogs_12m / avg_inventory, 2) if avg_inventory > 0.01 else 0.0

	avg_days_row = frappe.db.sql(
		f"""
		SELECT COALESCE(AVG(DATEDIFF(CURDATE(), latest.last_movement)), 0) AS avg_days
		FROM (
			SELECT sle.item_code, sle.warehouse, MAX(sle.posting_date) AS last_movement
			FROM `tabStock Ledger Entry` sle
			INNER JOIN `tabWarehouse` w ON w.name = sle.warehouse
			WHERE w.company = %s
			  {sle2_wh_sql}
			  AND sle.posting_date IS NOT NULL
			GROUP BY sle.item_code, sle.warehouse
		) latest
		WHERE latest.last_movement IS NOT NULL
		""",
		tuple([company] + sle2_wh_params),
		as_dict=True,
	)
	days_of_inventory = int((avg_days_row[0].avg_days if avg_days_row else 0) or 0)

	return {
		"value": round(value, 2),
		"stock_qty": round(stock_qty, 2),
		"available_value": round(available_value, 2),
		"reserved_value": round(reserved_value, 2),
		"turnover": turnover,
		"days_of_inventory": days_of_inventory,
		"low_stock_count": low_stock_count,
		"non_moving_count": non_moving_count,
	}
