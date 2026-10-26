"""Phase 3D — Collection performance (Payment Entry actuals; no targets)."""

from __future__ import annotations

from typing import Optional

import frappe

from erp_analysis.access_context import guard_mobile_api
from erp_analysis.services.collection import (
	get_collection_attention_payload,
	get_collection_dashboard_payload,
	get_customer_advances_by_customer,
	get_customer_advances_chart_series,
	get_customer_advances_summary,
	get_unallocated_payments,
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


@frappe.whitelist(methods=["GET", "POST"], allow_guest=False)
def get_customer_advances(
	company: Optional[str] = None,
	limit: Optional[int] = None,
	min_unallocated: Optional[float] = None,
	territory: Optional[str] = None,
	customer: Optional[str] = None,
):
	"""
	Open customer advances (unallocated Receive Payment Entries), scoped like receivables/collection.

	Optional ``customer`` returns payment-level rows for drill-down.
	"""
	ctx = guard_mobile_api(
		company=company,
		module_key="receivables",
		scope_module="receivables",
		territory=territory,
		object_key="erp_analysis.collection.get_customer_advances",
	)
	company = ctx["company"]
	territories = ctx["view_territory_scope"]
	limit = _to_int(_get_arg("limit", limit), 20)
	min_unallocated = float(_get_arg("min_unallocated", min_unallocated) or 0.01)
	territory = _get_arg("territory", territory)
	customer = _get_arg("customer", customer) or _get_arg("party", None)

	try:
		summary = get_customer_advances_summary(
			company=company,
			min_unallocated=min_unallocated,
			territory=territory,
			territories=territories,
		)
		if customer:
			payments = get_unallocated_payments(
				company=company,
				min_unallocated=min_unallocated,
				limit=limit,
				territories=territories,
				party=customer,
			)
			return {
				"summary": summary,
				"customer": customer,
				"payments": payments,
			}
		return {
			"summary": summary,
			"by_customer": get_customer_advances_by_customer(
				company=company,
				min_unallocated=min_unallocated,
				limit=limit,
				territory=territory,
				territories=territories,
			),
		}
	except Exception:
		frappe.log_error(title="collection.get_customer_advances", message=frappe.get_traceback())
		return {"summary": {"total_advance": 0, "customer_count": 0, "payment_count": 0}, "by_customer": []}


@frappe.whitelist(methods=["GET", "POST"], allow_guest=False)
def get_customer_advances_customers_chart(
	company: Optional[str] = None,
	limit: Optional[int] = None,
	territory: Optional[str] = None,
	min_unallocated: Optional[float] = None,
):
	"""Ranking/chart payload — top customers by unallocated advance (territory scope = receivables)."""
	ctx = guard_mobile_api(
		company=company,
		module_key="receivables",
		scope_module="receivables",
		territory=territory,
		object_key="erp_analysis.collection.get_customer_advances_customers_chart",
	)
	company = ctx["company"]
	territories = ctx["view_territory_scope"]
	limit = _to_int(_get_arg("limit", limit), 10)
	territory = _get_arg("territory", territory)
	min_unallocated = float(_get_arg("min_unallocated", min_unallocated) or 0.01)

	try:
		series = get_customer_advances_chart_series(
			company=company,
			limit=limit,
			territory=territory,
			territories=territories,
			min_unallocated=min_unallocated,
		)
	except Exception:
		frappe.log_error(
			title="collection.get_customer_advances_customers_chart",
			message=frappe.get_traceback(),
		)
		series = []

	return {
		"series": series,
		"meta": {
			"schema_version": 1,
			"chart_key": "customer_advances_customers",
			"dimension": "customer",
			"count": len(series),
		},
	}
