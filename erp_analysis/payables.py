"""Phase 3F — Accounts Payables dashboard and payment planning."""

from __future__ import annotations

from typing import Optional

import frappe

from erp_analysis.access_context import guard_mobile_api
from erp_analysis.services import payables as payables_service
from erp_analysis.utils.rpc import get_arg as _get_arg, to_bool as _to_bool, to_int as _to_int


@frappe.whitelist(methods=["GET", "POST"], allow_guest=False)
def get_payables_dashboard(
	company: Optional[str] = None,
	limit: Optional[int] = None,
	supplier: Optional[str] = None,
	include_invoices: Optional[int] = None,
	invoice_limit: Optional[int] = None,
):
	"""Payables dashboard — total/overdue AP, aging buckets, top suppliers, open invoice lines."""
	ctx = guard_mobile_api(company=company, module_key="payables")
	company = ctx["company"]
	limit = _to_int(_get_arg("limit", limit), 20)
	supplier = _get_arg("supplier", supplier)
	raw_include = _get_arg("include_invoices", include_invoices)
	if raw_include is None or str(raw_include).strip() == "":
		include_invoices = bool(supplier and str(supplier).strip())
	else:
		include_invoices = _to_bool(raw_include, True)
	invoice_limit = _to_int(_get_arg("invoice_limit", invoice_limit), 500)

	try:
		return payables_service.get_payables_dashboard_payload(
			company=company,
			limit=limit,
			supplier=supplier,
			include_invoices=include_invoices,
			invoice_limit=invoice_limit,
		)
	except Exception:
		frappe.log_error(title="payables.get_payables_dashboard", message=frappe.get_traceback())
		return {
			"kpis": {"total": 0, "overdue": 0, "overdue_pct": 0, "invoice_count": 0},
			"aging_buckets": {"current": 0, "d30": 0, "d60": 0, "d90": 0, "d120p": 0},
			"by_supplier": [],
			"invoices": [],
			"open_invoices": [],
		}


@frappe.whitelist(methods=["GET", "POST"], allow_guest=False)
def get_payment_planning(
	company: Optional[str] = None,
	days_ahead: Optional[int] = None,
	limit: Optional[int] = None,
):
	"""Payment planning — invoices due soon and overdue suppliers."""
	ctx = guard_mobile_api(company=company, module_key="payables")
	company = ctx["company"]
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
