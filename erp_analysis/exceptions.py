"""Phase 3J — Management exceptions (no target-miss rules)."""

from __future__ import annotations

from typing import Optional

import frappe

from erp_analysis.services import exceptions as exceptions_service
from erp_analysis.utils.rpc import get_arg as _get_arg, to_int as _to_int


@frappe.whitelist(methods=["GET", "POST"], allow_guest=False)
def get_management_exceptions(
	company: Optional[str] = None,
	limit: Optional[int] = None,
	stale_days: Optional[int] = None,
):
	"""
	Management exceptions — overdue AR, stale SO, low stock, pending approvals.

	Excludes target-miss rules per Phase 3 scope.
	"""
	company = _get_arg("company", company) or frappe.defaults.get_user_default("Company")
	limit = _to_int(_get_arg("limit", limit), 10)
	stale_days = _to_int(_get_arg("stale_days", stale_days), 90)

	try:
		return exceptions_service.get_management_exceptions_payload(
			company=company,
			limit=limit,
			stale_days=stale_days,
		)
	except Exception:
		frappe.log_error(title="exceptions.get_management_exceptions", message=frappe.get_traceback())
		return {
			"summary": {"overdue_ar": 0, "stale_so": 0, "low_stock": 0, "pending_approval": 0},
			"overdue_ar": [],
			"stale_so": [],
			"low_stock": [],
			"pending_approval": [],
			"unallocated_payments": [],
		}
