"""Phase 3D — Collection performance (Payment Entry actuals; no targets)."""

from __future__ import annotations

from typing import Optional

import frappe

from erp_analysis.access_context import guard_mobile_api
from erp_analysis.services.collection import (
	get_collection_attention_payload,
	get_collection_dashboard_payload,
)
from erp_analysis.utils.rpc import get_arg as _get_arg, to_int as _to_int


@frappe.whitelist(methods=["GET", "POST"], allow_guest=False)
def get_collection_dashboard(
	company: Optional[str] = None,
	from_date: Optional[str] = None,
	to_date: Optional[str] = None,
	territory: Optional[str] = None,
	limit: Optional[int] = None,
):
	"""
	Collection dashboard — today/MTD/YTD actuals plus territory and customer breakdowns.

	Data source: submitted Payment Entry (Receive), allocated amounts for breakdown tables.
	"""
	ctx = guard_mobile_api(
		company=company,
		module_key="collection",
		scope_module="sales",
		territory=territory,
	)
	company = ctx["company"]
	territories = ctx["view_territory_scope"]
	from_date = _get_arg("from_date", from_date)
	to_date = _get_arg("to_date", to_date)
	territory = _get_arg("territory", territory)
	limit = _to_int(_get_arg("limit", limit), 20)

	try:
		return get_collection_dashboard_payload(
			company=company,
			from_date=from_date,
			to_date=to_date,
			territory=territory,
			limit=limit,
			territories=territories,
		)
	except Exception:
		frappe.log_error(title="collection.get_collection_dashboard", message=frappe.get_traceback())
		return {
			"kpis": {"today": 0, "mtd": 0, "ytd": 0},
			"period": {"from_date": from_date, "to_date": to_date},
			"by_territory": [],
			"by_customer": [],
		}


@frappe.whitelist(methods=["GET", "POST"], allow_guest=False)
def get_collection_attention(
	company: Optional[str] = None,
	min_unallocated: Optional[float] = None,
	limit: Optional[int] = None,
):
	"""
	Collection attention lists — overdue customers and large unallocated payments.
	"""
	ctx = guard_mobile_api(company=company, module_key="collection", scope_module="receivables")
	company = ctx["company"]
	territories = ctx["view_territory_scope"]
	min_unallocated = float(_get_arg("min_unallocated", min_unallocated) or 100)
	limit = _to_int(_get_arg("limit", limit), 20)

	try:
		return get_collection_attention_payload(
			company=company,
			min_unallocated=min_unallocated,
			limit=limit,
			territories=territories,
		)
	except Exception:
		frappe.log_error(title="collection.get_collection_attention", message=frappe.get_traceback())
		return {"overdue_customers": [], "unallocated_payments": []}
