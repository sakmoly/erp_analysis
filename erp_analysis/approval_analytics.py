"""Phase 3K — Approval analytics summary."""

from __future__ import annotations

from typing import Optional

import frappe

from erp_analysis.services import approval_analytics as approval_analytics_service
from erp_analysis.utils.rpc import get_arg as _get_arg


@frappe.whitelist(methods=["GET", "POST"], allow_guest=False)
def get_approval_summary(
	company: Optional[str] = None,
	from_date: Optional[str] = None,
	to_date: Optional[str] = None,
):
	"""Approval analytics — pending counts by doctype, status, and aging."""
	company = _get_arg("company", company) or frappe.defaults.get_user_default("Company")
	from_date = _get_arg("from_date", from_date)
	to_date = _get_arg("to_date", to_date)

	try:
		return approval_analytics_service.get_approval_summary_payload(
			company=company,
			from_date=from_date,
			to_date=to_date,
		)
	except Exception:
		frappe.log_error(title="approval_analytics.get_approval_summary", message=frappe.get_traceback())
		return {
			"period": {"from_date": from_date, "to_date": to_date},
			"total_pending": 0,
			"total_amount": 0,
			"by_doctype": [],
			"by_status": [],
			"aging": {"0_7": 0, "8_30": 0, "31_plus": 0, "unknown": 0},
		}
