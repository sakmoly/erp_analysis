"""Replay division drill as Sakeer (Retail/Software + mobile-style params)."""

from __future__ import annotations

import json

import frappe

USER = "sakeer@printechs.com"
COMPANY = "Printechs Advanced Printing Trading Co."


def _call(**kwargs):
	return frappe.call("erp_analysis.api.get_dashboard_widget_data", **kwargs)


def run():
	frappe.set_user(USER)
	board = frappe.call(
		"erp_analysis.api.get_dashboard_board_data",
		dashboard_id="sales_overview",
		company=COMPANY,
		from_date="2026-01-01",
		to_date="2026-10-13",
		period="ytd",
		refresh=1,
	)
	div_w = (board.get("widgets") or {}).get("sales_by_division") or {}
	rows = div_w.get("rows") or (div_w.get("table") or {}).get("rows") or []
	print("Board divisions:", [(r.get("dimension") or r.get("label"), r.get("dimension_value")) for r in rows])

	scenarios = [
		{"division": ["Retail"], "label": "Retail drill_depth=1"},
		{"division": ["Software"], "label": "Software drill_depth=1"},
		{"division": ["Retail"], "territories": "Dammam,Riyadh,Jeddah", "label": "Retail + territories param"},
		{"channel": ["Retail"], "label": "Retail channel alias filter"},
	]

	for sc in scenarios:
		label = sc.pop("label")
		filters = {k: v for k, v in sc.items() if k not in ("territories",)}
		kw = dict(
			widget_key="sales_by_division",
			company=COMPANY,
			from_date="2026-01-01",
			to_date="2026-10-13",
			period="ytd",
			drill_depth=1,
			limit=10,
			filters=json.dumps(filters, separators=(",", ":")),
		)
		if sc.get("territories"):
			kw["territories"] = sc["territories"]
		try:
			out = _call(**kw)
			n = len(out.get("rows") or (out.get("table") or {}).get("rows") or [])
			print(f"OK {label}: rows={n} dim={out.get('meta', {}).get('dimension')}")
		except Exception as e:
			print(f"ERR {label}: {e!r}")

	# Brand step for first Retail sub_group
	try:
		out = _call(
			widget_key="sales_by_division",
			company=COMPANY,
			from_date="2026-01-01",
			to_date="2026-10-13",
			period="ytd",
			drill_depth=2,
			dimension="sub_group",
			filters=json.dumps(
				{"division": ["Retail"], "sub_group": ["Retail Systems"]},
				separators=(",", ":"),
			),
		)
		n = len(out.get("rows") or [])
		print(f"OK Retail->brand stale dim: rows={n} meta_dim={out.get('meta', {}).get('dimension')}")
	except Exception as e:
		print(f"ERR Retail->brand: {e!r}")

	frappe.set_user("Administrator")
