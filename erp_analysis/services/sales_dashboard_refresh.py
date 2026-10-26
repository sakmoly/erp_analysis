"""Mobile / desk: windowed refresh of tabSalesDashBoard (Printechs GP source)."""

from __future__ import annotations

from typing import Any, Optional

import frappe
from frappe import _

from erp_analysis.permissions.access_profile import PermissionDenied, evaluate, get_view_overrides

REFRESH_API_OBJECT_KEY = "erp_analysis.api.refresh_sales_dashboard"


def user_can_refresh_sales_dashboard(
	user: Optional[str] = None,
	company: Optional[str] = None,
) -> bool:
	"""Management: System Manager, company-wide sales view, or explicit API access."""
	user = user or frappe.session.user
	if not user or user == "Guest":
		return False
	if user == "Administrator" or "System Manager" in frappe.get_roles(user):
		return True

	if company is None:
		company = frappe.defaults.get_user_default("Company", user=user)

	if get_view_overrides(user, company).get("allow_view_all_sales"):
		return True

	if not company:
		return False

	try:
		decision = evaluate(user, company, None, None, REFRESH_API_OBJECT_KEY)
	except PermissionDenied:
		return False
	except Exception:
		frappe.log_error(title="sales_dashboard_refresh permission", message=frappe.get_traceback())
		return False

	return bool(decision.get("can_approve") or decision.get("can_view"))


def refresh_sales_dashboard_for_mobile(
	*,
	period: str = "daily",
	from_date: Optional[str] = None,
	to_date: Optional[str] = None,
	company: Optional[str] = None,
) -> dict[str, Any]:
	if not user_can_refresh_sales_dashboard(frappe.session.user, company):
		frappe.throw(_("Not permitted to refresh sales dashboard data."), frappe.PermissionError)

	from frappeauth_app.tasks import refresh_sales_dashboard_window

	result = refresh_sales_dashboard_window(
		period=period or "daily",
		from_date=from_date,
		to_date=to_date,
	)
	result["api"] = REFRESH_API_OBJECT_KEY
	return result
