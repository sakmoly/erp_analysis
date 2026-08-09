"""Phase 3I — Gross profit / profitability dashboard."""

from __future__ import annotations

from typing import Optional

import frappe

from erp_analysis.services import profitability as profitability_service
from erp_analysis.utils.rpc import get_arg as _get_arg, to_int as _to_int


@frappe.whitelist(methods=["GET", "POST"], allow_guest=False)
def get_gross_profit_dashboard(
	company: Optional[str] = None,
	period: Optional[str] = None,
	from_date: Optional[str] = None,
	to_date: Optional[str] = None,
	limit: Optional[int] = None,
):
	"""Gross profit dashboard — MTD/YTD KPIs plus territory/brand/division breakdown."""
	company = _get_arg("company", company) or frappe.defaults.get_user_default("Company")
	period = _get_arg("period", period)
	from_date = _get_arg("from_date", from_date)
	to_date = _get_arg("to_date", to_date)
	limit = _to_int(_get_arg("limit", limit), 10)

	try:
		return profitability_service.get_gross_profit_dashboard_payload(
			company=company,
			period=period,
			from_date=from_date,
			to_date=to_date,
			limit=limit,
		)
	except Exception:
		frappe.log_error(title="profitability.get_gross_profit_dashboard", message=frappe.get_traceback())
		return {
			"period": {"from_date": from_date, "to_date": to_date},
			"kpis": {"mtd": 0, "ytd": 0, "gp_pct_mtd": 0, "gp_pct_ytd": 0},
			"by_territory": [],
			"by_brand": [],
			"by_division": [],
		}


@frappe.whitelist(methods=["GET", "POST"], allow_guest=False)
def get_profitability_dashboard(
	company: Optional[str] = None,
	period: Optional[str] = None,
	from_date: Optional[str] = None,
	to_date: Optional[str] = None,
	limit: Optional[int] = None,
	**kwargs,
):
	"""Mobile path: erp_analysis.profitability.get_profitability_dashboard"""
	return get_gross_profit_dashboard(
		company=company,
		period=period,
		from_date=from_date,
		to_date=to_date,
		limit=limit,
	)
