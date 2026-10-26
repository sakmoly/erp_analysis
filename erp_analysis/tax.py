"""Mobile VAT dashboard — ZATCA-aligned output/input VAT with territory and not-submitted tracking."""

from __future__ import annotations

from typing import Any, Optional

import frappe

from erp_analysis.access_context import guard_mobile_api
from erp_analysis.services.sales_period import resolve_period_dates
from erp_analysis.services.vat_zatca import get_vat_dashboard_payload
from erp_analysis.utils.rpc import get_arg as _get_arg, to_bool as _to_bool, to_int as _to_int

VAT_API_OBJECT = "erp_analysis.tax.get_vat_dashboard"


@frappe.whitelist(methods=["GET", "POST"], allow_guest=False)
def get_vat_dashboard(
	company: Optional[str] = None,
	period: Optional[str] = None,
	from_date: Optional[str] = None,
	to_date: Optional[str] = None,
	territory: Optional[str] = None,
	include_documents: Any = None,
	bucket_key: Optional[str] = None,
	drill_bucket: Optional[str] = None,
	document_limit: Any = None,
	**kwargs: Any,
):
	"""
	Output + input VAT (ZATCA report logic), net VAT due, and not-submitted buckets.

	Territory is required for scoped users; filters **output VAT** (Sales Invoice).
	Input VAT (Purchase Invoice) stays **company-wide** (PI has no territory field).

	Optional: ``include_documents=1``, ``bucket_key`` / ``drill_bucket`` for invoice lines.
	"""
	_get_arg("company", company)  # allow JSON body keys via kwargs in rpc helpers
	ctx = guard_mobile_api(
		company=company,
		object_key=VAT_API_OBJECT,
		territory=territory,
		scope_module="sales",
	)
	company = ctx["company"]
	territories = ctx["view_territory_scope"]

	period = _get_arg("period", period) or kwargs.get("period")
	from_date = _get_arg("from_date", from_date) or kwargs.get("from_date")
	to_date = _get_arg("to_date", to_date) or kwargs.get("to_date")
	territory = _get_arg("territory", territory) or kwargs.get("territory")

	start, end, period_key = resolve_period_dates(from_date, to_date, period=period)
	include_docs = _to_bool(
		_get_arg("include_documents", include_documents) or kwargs.get("include_documents"),
		False,
	)
	bucket = (
		_get_arg("bucket_key", bucket_key)
		or _get_arg("drill_bucket", drill_bucket)
		or kwargs.get("bucket_key")
		or kwargs.get("drill_bucket")
	)
	doc_limit = _to_int(
		_get_arg("document_limit", document_limit) or kwargs.get("document_limit"),
		500,
	)

	try:
		return get_vat_dashboard_payload(
			company=company,
			from_date=start,
			to_date=end,
			period_key=period_key,
			territories=territories,
			include_documents=include_docs,
			bucket_key=str(bucket).strip() if bucket else None,
			document_limit=doc_limit,
		)
	except Exception:
		frappe.log_error(title="tax.get_vat_dashboard", message=frappe.get_traceback())
		raise


@frappe.whitelist(methods=["GET", "POST"], allow_guest=False)
def get_vat_summary(**kwargs: Any):
	"""Alias for mobile clients expecting get_vat_summary."""
	return get_vat_dashboard(**kwargs)
