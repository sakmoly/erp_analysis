"""Verify home + sales_overview board batch (timing, catalog keys, LY)."""

from __future__ import annotations

import json
import time
from typing import Any

import frappe

from erp_analysis.services.mobile_widgets import clear_dashboard_board_cache, get_dashboard_board_data

HOME_SLOTS = [
	"home_total_sales_kpi",
	"home_total_receivables_kpi",
	"home_total_inventory_kpi",
	"home_total_purchases_kpi",
	"home_total_payables_kpi",
	"home_gross_profit_kpi",
	"home_gp_margin_kpi",
	"home_current_ratio_kpi",
	"home_operating_cash_flow_kpi",
	"home_net_profit_kpi",
	"home_sales_health",
	"home_receivables_health",
	"home_inventory_health",
	"home_payables_health",
	"home_trend_overview",
	"home_quick_insights",
	"home_recent_activities",
]
SALES_SLOTS = [
	"sales_total_kpi",
	"sales_orders_kpi",
	"sales_gp_kpi",
	"sales_cogs_kpi",
	"sales_gp_margin_kpi",
	"sales_active_customers_kpi",
	"sales_returns_kpi",
	"sales_trend_line",
	"sales_by_territory",
	"sales_by_division",
	"sales_by_salesperson",
	"sales_management_attention",
]
LY_KPI_KEYS = ["home_total_sales_kpi", "sales_total_kpi", "sales_gp_kpi"]


def _widget_nonempty(w: Any) -> bool:
	if not w or not isinstance(w, dict):
		return False
	if w.get("value") is not None:
		return True
	if w.get("kpis"):
		k0 = (w.get("kpis") or [{}])[0]
		if k0.get("value") is not None:
			return True
	chart = w.get("chart") or {}
	if chart.get("series") or chart.get("summary"):
		return True
	table = w.get("table") or {}
	if table.get("rows"):
		return True
	if w.get("rows") or w.get("items"):
		return True
	if w.get("widget_type") == "LIST" and w.get("data"):
		return True
	return False


def _has_ly(w: Any) -> bool:
	if not w:
		return False
	k = w.get("kpi") or {}
	if k.get("change_pct") is not None or k.get("value_ly") is not None:
		return True
	for row in w.get("kpis") or []:
		if row.get("change_pct") is not None or row.get("value_ly") is not None or row.get("previous") is not None:
			return True
	chart = w.get("chart") or {}
	summary = chart.get("summary") or {}
	if summary.get("value_ly") is not None or summary.get("change_pct") is not None:
		return True
	return False


def _run_board(user: str, company: str, dashboard_id: str) -> dict[str, Any]:
	kwargs = dict(
		user=user,
		dashboard_id=dashboard_id,
		company=company,
		from_date="2026-01-01",
		to_date="2026-10-26",
		period="ytd",
		show_ly=1,
	)
	clear_dashboard_board_cache()
	t0 = time.perf_counter()
	cold = get_dashboard_board_data(**kwargs, refresh=1, use_cache=True)
	cold_ms = (time.perf_counter() - t0) * 1000
	t1 = time.perf_counter()
	get_dashboard_board_data(**kwargs, refresh=0, use_cache=True)
	warm_ms = (time.perf_counter() - t1) * 1000
	widgets = cold.get("widgets") or {}
	slots = HOME_SLOTS if dashboard_id == "home" else SALES_SLOTS
	missing = [k for k in slots if k not in widgets]
	empty = [k for k in slots if k in widgets and not _widget_nonempty(widgets[k])]
	ly_ok = {k: _has_ly(widgets.get(k)) for k in LY_KPI_KEYS if k in widgets}
	return {
		"dashboard_id": dashboard_id,
		"cold_ms": round(cold_ms, 0),
		"warm_ms": round(warm_ms, 0),
		"widget_key_count": len(widgets),
		"meta_widget_count": (cold.get("meta") or {}).get("widget_count"),
		"catalog_slots": len(slots),
		"catalog_present": len(slots) - len(missing),
		"catalog_missing": missing,
		"catalog_empty": empty,
		"ly_kpis": ly_ok,
		"errors": cold.get("errors"),
	}


def _access_checks(user: str) -> dict[str, Any]:
	out: dict[str, Any] = {"registry": {}, "profile_rules": {}}
	for key in (
		"erp_analysis.api.get_dashboard_board_data",
		"erp_analysis.api.get_dashboard_widget_data",
		"erp_analysis.api.get_mobile_bootstrap",
	):
		out["registry"][key] = frappe.db.get_value(
			"Access Object Registry", {"object_key": key}, ["name", "is_active"], as_dict=True
		)
	profile = frappe.db.get_value("Access Profile", {"user": user, "enabled": 1}, "name")
	out["access_profile"] = profile
	if not profile:
		return out
	for key in (
		"erp_analysis.api.get_dashboard_board_data",
		"erp_analysis.api.get_dashboard_widget_data",
	):
		reg_name = frappe.db.get_value("Access Object Registry", {"object_key": key}, "name")
		if not reg_name:
			out["profile_rules"][key] = "no_registry_row"
			continue
		out["profile_rules"][key] = frappe.db.get_value(
			"Access Profile Line",
			{"parent": profile, "access_object": reg_name},
			["can_view", "active"],
			as_dict=True,
		)
	return out


def verify(user: str = "sakeer@printechs.com", company: str | None = None):
	frappe.set_user(user)
	if not company:
		from erp_analysis.api import _get_my_access

		access = _get_my_access(user=user)
		company = (access.get("scope") or {}).get("company") or frappe.defaults.get_user_default("Company")
	result = {
		"user": user,
		"company": company,
		"boards": [_run_board(user, company, "home"), _run_board(user, company, "sales_overview")],
		"access": _access_checks(user),
	}
	print(json.dumps(result, indent=2, default=str))
	return result
