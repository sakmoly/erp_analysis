"""Reconcile Software division row vs sub_group drill (BA)."""

from __future__ import annotations

import json

import frappe

USER = "sakeer@printechs.com"
COMPANY = "Printechs Advanced Printing Trading Co."


def _sum_rows(payload: dict) -> float:
	total = 0.0
	rows = payload.get("rows") or (payload.get("table") or {}).get("rows") or []
	for row in rows:
		total += float(row.get("metric") or row.get("total_sales") or row.get("value") or 0)
	return total


def _software_metric(payload: dict) -> float | None:
	rows = payload.get("rows") or (payload.get("table") or {}).get("rows") or []
	for row in rows:
		label = (row.get("label") or row.get("dimension") or "").strip()
		if label.startswith("Software"):
			return float(row.get("metric") or row.get("total_sales") or 0)
	return None


def run(
	user: str = USER,
	company: str = COMPANY,
	territory: str = "Dammam",
	period: str = "ytd",
	from_date: str | None = None,
	to_date: str | None = None,
):
	frappe.set_user(user)
	filters = json.dumps({"territory": [territory]}, separators=(",", ":"))
	kwargs = {
		"widget_key": "sales_by_division",
		"company": company,
		"period": period,
		"from_date": from_date,
		"to_date": to_date,
		"drill_depth": 0,
		"use_cache": 0,
		"filters": filters,
	}
	board = frappe.call("erp_analysis.api.get_dashboard_widget_data", **kwargs)
	sw = _software_metric(board)
	print(f"[depth=0] Software row metric={sw} filters={filters} period={period}")
	print(f"  meta dates={board.get('meta', {}).get('from_date')}..{board.get('meta', {}).get('to_date')}")

	kwargs["drill_depth"] = 1
	kwargs["dimension"] = "sub_group"
	kwargs["filters"] = json.dumps({"division": ["Software"], "territory": [territory]}, separators=(",", ":"))
	drill = frappe.call("erp_analysis.api.get_dashboard_widget_data", **kwargs)
	sub_sum = _sum_rows(drill)
	print(f"[depth=1] sub_group sum={sub_sum} rows={len(drill.get('rows') or [])}")
	for row in drill.get("rows") or []:
		print(f"  - {row.get('label')}: {row.get('metric') or row.get('total_sales')}")
	print(f"  applied filters={drill.get('meta', {}).get('filters') or drill.get('table', {}).get('filters')}")

	drill_api = frappe.call(
		"erp_analysis.api.get_sales_by_division_drill",
		company=company,
		period=period,
		from_date=from_date,
		to_date=to_date,
		drill_depth=1,
		filters=kwargs["filters"],
	)
	print(f"[drill API] sum={_sum_rows(drill_api)} dimension={drill_api.get('dimension')}")

	if sw and sub_sum:
		pct = abs(sub_sum - sw) / sw * 100 if sw else 0
		print(f"Delta: {sub_sum - sw:.2f} ({pct:.1f}%)")

