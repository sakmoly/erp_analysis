"""Approvals pending count for executive dashboard."""

from __future__ import annotations

from typing import Optional

import frappe


def get_pending_approvals_count(company: Optional[str] = None) -> int:
	"""Reuse approvals aggregation for a consistent pending count."""
	try:
		from erp_analysis.approvals import get_all_approvals

		result = get_all_approvals(company=company, limit=500)
		message = result.get("message") if isinstance(result, dict) else {}
		if isinstance(message, dict):
			return int(message.get("total_pending") or 0)
	except Exception:
		frappe.log_error(title="executive.approvals_count", message=frappe.get_traceback())
	return 0
