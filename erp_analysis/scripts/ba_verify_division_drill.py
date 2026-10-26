"""
BA verification: division board + depth-1 drill + product-performance fallback.

Run as test user:
  bench --site <site> execute erp_analysis.scripts.ba_verify_division_drill.run
"""

from __future__ import annotations

import json

import frappe

USER = "sakeer@printechs.com"
COMPANY = "Printechs Advanced Printing Trading Co."
FROM_DATE = "2026-01-01"
TO_DATE = "2026-10-13"
DIVISIONS = ("Industrial", "Retail", "Software")
DIVISION = "Industrial"
# Division-wide Industrial brands (missing sub_group) — Hitachi ~9.38M YTD on Printechs B2B.
DIVISION_WIDE_HITACHI_MIN = 9_000_000
# Per sub_group scoped brand totals (SalesDashBoard YTD 2026-01-01 → site to_date).
BRAND_DRILL_CASES = (
	{
		"sub_group": "Industrial Systems",
		"hitachi_min": 1_500_000,
		"hitachi_max": 2_500_000,
	},
	{
		"sub_group": "Industrial Consumables",
		"hitachi_min": 5_500_000,
		"hitachi_max": 6_500_000,
	},
)


def _row_count(payload: dict) -> int:
	return len(payload.get("rows") or (payload.get("table") or {}).get("rows") or [])


def _hitachi_metric(payload: dict) -> float | None:
	rows = payload.get("rows") or (payload.get("table") or {}).get("rows") or []
	for row in rows:
		label = (row.get("dimension") or row.get("label") or "").strip()
		if label == "Hitachi":
			return float(row.get("metric") or row.get("total_sales") or 0)
	return None


def _brand_drill_body(sub_group: str) -> dict:
	return {
		"widget_key": "sales_by_division",
		"company": COMPANY,
		"from_date": FROM_DATE,
		"to_date": TO_DATE,
		"period": "ytd",
		"drill_depth": 2,
		"dimension": "brand",
		"show_ly": 0,
		"filters": json.dumps(
			{"division": [DIVISION], "sub_group": [sub_group]},
			separators=(",", ":"),
		),
	}


def run(user: str = USER, company: str = COMPANY):
	frappe.set_user(user)
	print("User:", user, "Company:", company)
	print("Dates:", FROM_DATE, "→", TO_DATE, "period=ytd\n")

	board = frappe.call(
		"erp_analysis.api.get_dashboard_board_data",
		dashboard_id="sales_overview",
		company=company,
		from_date=FROM_DATE,
		to_date=TO_DATE,
		period="ytd",
		refresh=1,
		use_cache=0,
	)
	div_w = (board.get("widgets") or {}).get("sales_by_division") or {}
	board_rows = _row_count(div_w)
	print(f"[1] Board sales_by_division rows: {board_rows}")
	if board_rows == 0:
		print("FAIL: board has no division rows")
		return

	# Software + Dammam: sub_group sum must match division row (same period/filters).
	sw_filters = json.dumps({"division": ["Software"], "territory": ["Dammam"]}, separators=(",", ":"))
	sw_drill = frappe.call(
		"erp_analysis.api.get_sales_by_division_drill",
		company=company,
		from_date=FROM_DATE,
		to_date=TO_DATE,
		period="ytd",
		drill_depth=1,
		filters=sw_filters,
	)
	rec = sw_drill.get("reconcile") or {}
	if rec:
		ok = sw_drill.get("reconcile_ok")
		print(
			f"[2b] Software/Dammam reconcile: {'PASS' if ok else 'FAIL'} "
			f"division={rec.get('division_net_sales_total')} "
			f"rows={rec.get('sub_group_rows_sum')} delta={rec.get('delta')}"
		)

	for division in DIVISIONS:
		body = {
			"widget_key": "sales_by_division",
			"company": company,
			"from_date": FROM_DATE,
			"to_date": TO_DATE,
			"period": "ytd",
			"drill_depth": 1,
			"dimension": "sub_group",
			"show_ly": 0,
			"view_all_sales": 1,
			"filters": json.dumps({"division": [division]}, separators=(",", ":")),
		}
		drill = frappe.call("erp_analysis.api.get_dashboard_widget_data", **body)
		n = _row_count(drill)
		status = "PASS" if n > 0 else "FAIL"
		print(f"[2] Drill {division}: {status} rows={n} meta.dimension={drill.get('meta', {}).get('dimension')}")

		try:
			fallback = frappe.call(
				"erp_analysis.sales.get_product_performance",
				company=company,
				from_date=FROM_DATE,
				to_date=TO_DATE,
				level="item_group",
				division=division,
			)
			fn = len((fallback or {}).get("rows") or [])
			fstatus = "PASS" if fn > 0 else "FAIL"
			print(
				f"[3] Fallback get_product_performance item_group+division={division}: "
				f"{fstatus} rows={fn} group_by={(fallback or {}).get('group_by')}"
			)
		except Exception as exc:
			print(f"[3] Fallback {division}: FAIL ({exc})")

	print("\n[4] Brand drill (depth 2) — scoped by division + sub_group")
	print(
		"    PASS body template: drill_depth=2, dimension=brand, filters="
		'{"division":["Industrial"],"sub_group":["<Sub_Group from row>"]}'
	)
	for case in BRAND_DRILL_CASES:
		sub_group = case["sub_group"]
		filters_json = json.dumps(
			{"division": [DIVISION], "sub_group": [sub_group]},
			separators=(",", ":"),
		)
		body = _brand_drill_body(sub_group)

		widget = frappe.call("erp_analysis.api.get_dashboard_widget_data", **body)
		w_hitachi = _hitachi_metric(widget)
		w_rows = _row_count(widget)
		w_applied = (widget.get("table") or {}).get("filters") or {}

		product = frappe.call(
			"erp_analysis.sales.get_product_performance",
			company=company,
			from_date=FROM_DATE,
			to_date=TO_DATE,
			period="ytd",
			level="brand",
			limit=15,
			filters=filters_json,
		)
		p_hitachi = _hitachi_metric(product)

		drill_api = frappe.call(
			"erp_analysis.api.get_sales_by_division_drill",
			company=company,
			from_date=FROM_DATE,
			to_date=TO_DATE,
			period="ytd",
			drill_depth=2,
			limit=15,
			filters=filters_json,
		)
		d_hitachi = _hitachi_metric(drill_api)
		d_source = drill_api.get("data_source")

		division_wide = (
			w_hitachi is not None and w_hitachi >= DIVISION_WIDE_HITACHI_MIN
		) or (p_hitachi is not None and p_hitachi >= DIVISION_WIDE_HITACHI_MIN)
		in_range = (
			w_hitachi is not None
			and case["hitachi_min"] <= w_hitachi <= case["hitachi_max"]
			and p_hitachi is not None
			and case["hitachi_min"] <= p_hitachi <= case["hitachi_max"]
			and d_hitachi is not None
			and case["hitachi_min"] <= d_hitachi <= case["hitachi_max"]
		)
		status = "FAIL" if division_wide or not in_range or w_rows == 0 else "PASS"

		print(f"\n  sub_group={sub_group!r} → {status}")
		print(f"    filters sent: {filters_json}")
		print(f"    widget applied filters: {w_applied}")
		print(f"    widget Hitachi: {w_hitachi:,.2f}" if w_hitachi is not None else "    widget Hitachi: (missing)")
		print(f"    product_perf Hitachi: {p_hitachi:,.2f}" if p_hitachi is not None else "    product_perf Hitachi: (missing)")
		print(
			f"    get_sales_by_division_drill Hitachi: {d_hitachi:,.2f} (source={d_source})"
			if d_hitachi is not None
			else f"    get_sales_by_division_drill Hitachi: (missing) source={d_source}"
		)
		print(f"    widget rows: {w_rows}")
		if division_wide:
			print(
				"    → Division-wide scope (~9.38M Hitachi). "
				"Check server: sales.get_product_performance must forward sub_group; "
				"not a missing mobile filter if request matches above."
			)
		elif not in_range:
			print(
				f"    → Expected Hitachi between {case['hitachi_min']:,.0f} and {case['hitachi_max']:,.0f} "
				"(SalesDashBoard); compare tabSalesDashBoard Sub_Group values."
			)

	frappe.set_user("Administrator")
	print("\nDone.")
