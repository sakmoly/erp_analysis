"""Print sales overview KPI from bootstrap + board batch (mobile paths)."""

from __future__ import annotations

import frappe


def run(user: str = "sakeer@printechs.com", company: str = "Printechs Advanced Printing Trading Co."):
	frappe.set_user(user)
	from erp_analysis.services.mobile_bootstrap import build_mobile_bootstrap

	boot = build_mobile_bootstrap(user=user, company=company, hydrate=True)
	bd = (boot.get("board_data") or {}).get("sales_overview") or {}
	widgets = bd.get("widgets") or {}
	print("=== bootstrap board_data ===")
	for k in sorted(widgets.keys()):
		if "net" in k or "total" in k:
			w = widgets[k]
			print(k, "value=", w.get("value"), "data_source=", (w.get("meta") or {}).get("data_source"))

	board = frappe.call(
		"erp_analysis.api.get_dashboard_board_data",
		dashboard_id="sales_overview",
		company=company,
		period="ytd",
		use_cache=True,
		refresh=False,
	)
	print("\n=== board batch (cached) ===")
	for k in ("sales_total_kpi", "sales_dash_net_ytd_kpi"):
		w = (board.get("widgets") or {}).get(k) or {}
		print(k, "value=", w.get("value"), "data_source=", (w.get("meta") or {}).get("data_source"))

	frappe.set_user("Administrator")
