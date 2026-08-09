"""Phase 3A — Executive Dashboard 2.0 (additive; does not replace v1 dashboard)."""

from __future__ import annotations

from typing import Any, Optional

import frappe

from erp_analysis.services.kpi.approvals_summary import get_pending_approvals_count
from erp_analysis.services.kpi.collection import get_collection_period_kpis
from erp_analysis.services.kpi.gross_profit import get_gross_profit_period_kpis
from erp_analysis.services.kpi.inventory_summary import get_inventory_summary_kpis
from erp_analysis.services.kpi.receivables_summary import get_receivables_summary_kpis
from erp_analysis.services.kpi.sales import get_sales_period_kpis
from erp_analysis.services.payables import get_payables_summary
from erp_analysis.services.purchase import get_purchase_summary
from erp_analysis.services.sales_orders import get_order_book_summary


def _empty_executive_dashboard() -> dict[str, Any]:
	return {
		"sales": {
			"today": 0,
			"mtd": 0,
			"ytd": 0,
			"mtd_ly": 0,
			"ytd_ly": 0,
			"mtd_change_pct": 0,
			"ytd_change_pct": 0,
		},
		"gross_profit": {"mtd": 0, "ytd": 0, "gp_pct_mtd": 0, "gp_pct_ytd": 0},
		"collection": {"today": 0, "mtd": 0, "ytd": 0},
		"receivables": {"total": 0, "overdue": 0, "overdue_pct": 0},
		"inventory": {"value": 0, "low_stock_count": 0, "non_moving_count": 0},
		"orders": {
			"open_count": 0,
			"open_value": 0,
			"pending_delivery_count": 0,
			"pending_delivery_value": 0,
		},
		"purchasing": {
			"open_count": 0,
			"open_value": 0,
			"pending_receipt_count": 0,
			"pending_receipt_value": 0,
		},
		"payables": {"total": 0, "overdue": 0, "overdue_pct": 0},
		"approvals": {"pending_count": 0},
	}


def _safe(section: str, fn, default):
	try:
		return fn()
	except Exception:
		frappe.log_error(title=f"executive.{section}", message=frappe.get_traceback())
		return default


@frappe.whitelist(methods=["GET", "POST"], allow_guest=False)
def get_executive_dashboard(
	company: Optional[str] = None,
	from_date: Optional[str] = None,
	to_date: Optional[str] = None,
	territory: Optional[str] = None,
	territories: Optional[str] = None,
	branch: Optional[str] = None,
):
	"""
	Executive Dashboard 2.0 — actuals only (no targets, no cash/bank).

	`territories` = comma-separated **view** territories (do not fall back to Employee.branch).
	"""
	from erp_analysis.permissions.access_profile import resolve_territory_scope

	company = company or frappe.defaults.get_user_default("Company")
	territories = territories or frappe.form_dict.get("territories")
	sales_scope = resolve_territory_scope(
		requested=territory,
		requested_list=territories,
		company=company,
		purpose="view",
		module="sales",
	)
	ar_scope = resolve_territory_scope(
		requested=territory,
		requested_list=territories,
		company=company,
		purpose="view",
		module="receivables",
	)
	# Pass first territory only into helpers that take a single name; prefer list via kwargs where supported
	territory_arg = territory
	if sales_scope and len(sales_scope) == 1:
		territory_arg = sales_scope[0]

	payload = _empty_executive_dashboard()

	payload["sales"] = _safe(
		"sales",
		lambda: get_sales_period_kpis(
			company=company, as_of=to_date, territory=territory_arg, territories=sales_scope
		),
		payload["sales"],
	)
	payload["gross_profit"] = _safe(
		"gross_profit",
		lambda: get_gross_profit_period_kpis(
			company=company,
			as_of=to_date,
			territory=territory_arg,
			territories=sales_scope,
		),
		payload["gross_profit"],
	)
	payload["collection"] = _safe(
		"collection",
		lambda: get_collection_period_kpis(
			company=company,
			as_of=to_date,
			territory=territory_arg,
			territories=sales_scope,
		),
		payload["collection"],
	)
	payload["receivables"] = _safe(
		"receivables",
		lambda: get_receivables_summary_kpis(
			company=company, territory=territory_arg, territories=ar_scope
		),
		payload["receivables"],
	)
	payload["inventory"] = _safe(
		"inventory",
		lambda: get_inventory_summary_kpis(company=company),
		payload["inventory"],
	)
	payload["approvals"] = {
		"pending_count": _safe(
			"approvals",
			lambda: get_pending_approvals_count(company=company),
			0,
		)
	}
	payload["orders"] = _safe(
		"orders",
		lambda: get_order_book_summary(
			company=company, territory=territory_arg, territories=sales_scope
		),
		payload["orders"],
	)
	payload["purchasing"] = _safe(
		"purchasing",
		lambda: get_purchase_summary(company=company),
		payload["purchasing"],
	)
	payload["payables"] = _safe(
		"payables",
		lambda: get_payables_summary(company=company),
		payload["payables"],
	)

	return payload
