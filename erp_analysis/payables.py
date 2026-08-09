"""Phase 3F — Accounts Payables dashboard and payment planning."""

from __future__ import annotations

from typing import Optional

import frappe

from erp_analysis.services import payables as payables_service
from erp_analysis.utils.rpc import get_arg as _get_arg, to_int as _to_int


@frappe.whitelist(methods=["GET", "POST"], allow_guest=False)
def get_payables_dashboard(
	company: Optional[str] = None,
	limit: Optional[int] = None,
):
	"""Payables dashboard — total/overdue AP, aging buckets, top suppliers."""
	company = _get_arg("company", company) or frappe.defaults.get_user_default("Company")
	limit = _to_int(_get_arg("limit", limit), 20)

	try:
		return payables_service.get_payables_dashboard_payload(company=company, limit=limit)
	except Exception:
		frappe.log_error(title="payables.get_payables_dashboard", message=frappe.get_traceback())
		return {
			"kpis": {"total": 0, "overdue": 0, "overdue_pct": 0, "invoice_count": 0},
			"aging_buckets": {"current": 0, "d30": 0, "d60": 0, "d90": 0, "d120p": 0},
			"by_supplier": [],
		}


@frappe.whitelist(methods=["GET", "POST"], allow_guest=False)
def get_payment_planning(
	company: Optional[str] = None,
	days_ahead: Optional[int] = None,
	limit: Optional[int] = None,
):
	"""Payment planning — invoices due soon and overdue suppliers."""
	company = _get_arg("company", company) or frappe.defaults.get_user_default("Company")
	days_ahead = _to_int(_get_arg("days_ahead", days_ahead), 30)
	limit = _to_int(_get_arg("limit", limit), 20)

	try:
		return payables_service.get_payment_planning_payload(
			company=company,
			days_ahead=days_ahead,
			limit=limit,
		)
	except Exception:
		frappe.log_error(title="payables.get_payment_planning", message=frappe.get_traceback())
		return {"days_ahead": days_ahead, "due_soon": [], "overdue_suppliers": []}
