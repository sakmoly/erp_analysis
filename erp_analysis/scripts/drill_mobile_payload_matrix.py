"""Try mobile-like drill payloads for sales_by_division → Industrial."""

from __future__ import annotations

import json

import frappe

USER = "sakeer@printechs.com"
COMPANY = "Printechs Advanced Printing Trading Co."


def _count(p: dict) -> int:
	return len(p.get("rows") or (p.get("table") or {}).get("rows") or [])


def run():
	frappe.set_user(USER)
	cases = [
		{
			"label": "BA canonical",
			"kwargs": {
				"widget_key": "sales_by_division",
				"company": COMPANY,
				"from_date": "2026-01-01",
				"to_date": "2026-10-13",
				"period": "ytd",
				"drill_depth": 1,
				"dimension": "sub_group",
				"filters": json.dumps({"division": ["Industrial"]}),
			},
		},
		{
			"label": "slice key industrial",
			"kwargs": {
				"widget_key": "sales_by_division",
				"company": COMPANY,
				"from_date": "2026-01-01",
				"to_date": "2026-10-13",
				"period": "ytd",
				"drill_depth": 1,
				"dimension": "sub_group",
				"filters": json.dumps({"industrial": ["Industrial"]}),
			},
		},
		{
			"label": "no dates period ytd only",
			"kwargs": {
				"widget_key": "sales_by_division",
				"company": COMPANY,
				"period": "ytd",
				"drill_depth": 1,
				"dimension": "sub_group",
				"filters": {"division": ["Industrial"]},
			},
		},
		{
			"label": "stale dimension division at depth 1",
			"kwargs": {
				"widget_key": "sales_by_division",
				"company": COMPANY,
				"from_date": "2026-01-01",
				"to_date": "2026-10-13",
				"period": "ytd",
				"drill_depth": 1,
				"dimension": "division",
				"filters": json.dumps({"division": ["Industrial"]}),
			},
		},
		{
			"label": "item_group dimension",
			"kwargs": {
				"widget_key": "sales_by_division",
				"company": COMPANY,
				"from_date": "2026-01-01",
				"to_date": "2026-10-13",
				"period": "ytd",
				"drill_depth": 1,
				"dimension": "item_group",
				"filters": json.dumps({"division": ["Industrial"]}),
			},
		},
		{
			"label": "no drill_depth dimension sub_group",
			"kwargs": {
				"widget_key": "sales_by_division",
				"company": COMPANY,
				"from_date": "2026-01-01",
				"to_date": "2026-10-13",
				"period": "ytd",
				"dimension": "sub_group",
				"filters": json.dumps({"division": ["Industrial"]}),
			},
		},
		{
			"label": "channel widget alias",
			"kwargs": {
				"widget_key": "sales_by_channel",
				"company": COMPANY,
				"from_date": "2026-01-01",
				"to_date": "2026-10-13",
				"period": "ytd",
				"drill_depth": 1,
				"dimension": "sub_group",
				"filters": json.dumps({"division": ["Industrial"]}),
			},
		},
	]
	for case in cases:
		try:
			p = frappe.call("erp_analysis.api.get_dashboard_widget_data", **case["kwargs"])
			n = _count(p)
			dim = (p.get("meta") or {}).get("dimension") or (p.get("table") or {}).get("dimension")
			print(f"{case['label']}: rows={n} dimension={dim} empty={ (p.get('meta') or {}).get('empty_state')}")
		except Exception as exc:
			print(f"{case['label']}: ERROR {exc}")
	frappe.set_user("Administrator")
