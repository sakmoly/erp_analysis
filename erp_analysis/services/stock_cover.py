"""Stock cover — days of supply from recent sales velocity."""

from __future__ import annotations

from typing import Any, Optional

import frappe


def get_stock_cover_payload(
	company: Optional[str] = None,
	warehouse: Optional[str] = None,
	lookback_days: int = 90,
	low_cover_threshold: float = 7.0,
	limit: int = 20,
) -> dict[str, Any]:
	company = company or frappe.defaults.get_user_default("Company")
	if not company:
		return {
			"kpis": {"avg_cover_days": 0, "low_cover_count": 0, "excess_cover_count": 0},
			"low_cover_items": [],
		}

	warehouse_sql = ""
	params: list[Any] = [company, int(lookback_days), company]
	if warehouse:
		warehouse_sql = " AND b.warehouse = %s"
		params.append(warehouse)

	rows = frappe.db.sql(
		f"""
		SELECT
			b.item_code,
			COALESCE(i.item_name, b.item_code) AS item_name,
			COALESCE(i.item_group, '') AS item_group,
			b.warehouse,
			COALESCE(SUM(b.actual_qty), 0) AS on_hand_qty,
			COALESCE(SUM(b.actual_qty * COALESCE(b.valuation_rate, 0)), 0) AS stock_value,
			COALESCE(sales.sold_qty, 0) AS sold_qty
		FROM `tabBin` b
		INNER JOIN `tabWarehouse` w ON w.name = b.warehouse
		LEFT JOIN `tabItem` i ON i.name = b.item_code
		LEFT JOIN (
			SELECT
				sii.item_code,
				SUM(sii.qty) AS sold_qty
			FROM `tabSales Invoice Item` sii
			INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
			WHERE si.docstatus = 1
			  AND si.company = %s
			  AND si.posting_date >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
			GROUP BY sii.item_code
		) sales ON sales.item_code = b.item_code
		WHERE w.company = %s
		  AND b.actual_qty > 0
		  {warehouse_sql}
		GROUP BY b.item_code, i.item_name, i.item_group, b.warehouse, sales.sold_qty
		""",
		tuple(params),
		as_dict=True,
	)

	lookback = max(int(lookback_days), 1)
	low_threshold = float(low_cover_threshold)
	excess_threshold = lookback * 2

	item_rows: list[dict[str, Any]] = []
	cover_values: list[float] = []
	low_cover_count = 0
	excess_cover_count = 0

	for row in rows:
		on_hand = float(row.on_hand_qty or 0)
		sold = float(row.sold_qty or 0)
		daily_sales = sold / lookback if sold > 0 else 0
		if daily_sales > 0:
			cover_days = round(on_hand / daily_sales, 1)
		else:
			cover_days = None

		entry = {
			"item_code": row.item_code,
			"item_name": row.item_name,
			"item_group": row.item_group,
			"warehouse": row.warehouse,
			"on_hand_qty": round(on_hand, 2),
			"stock_value": round(float(row.stock_value or 0), 2),
			"sold_qty": round(sold, 2),
			"cover_days": cover_days,
		}
		item_rows.append(entry)

		if cover_days is None:
			excess_cover_count += 1
			continue
		cover_values.append(cover_days)
		if cover_days < low_threshold:
			low_cover_count += 1
		if cover_days > excess_threshold:
			excess_cover_count += 1

	avg_cover = round(sum(cover_values) / len(cover_values), 1) if cover_values else 0
	low_cover_items = sorted(
		[r for r in item_rows if r["cover_days"] is not None and r["cover_days"] < low_threshold],
		key=lambda x: x["cover_days"],
	)[: int(limit)]

	return {
		"lookback_days": lookback,
		"low_cover_threshold": low_threshold,
		"kpis": {
			"avg_cover_days": avg_cover,
			"low_cover_count": low_cover_count,
			"excess_cover_count": excess_cover_count,
		},
		"low_cover_items": low_cover_items,
	}
