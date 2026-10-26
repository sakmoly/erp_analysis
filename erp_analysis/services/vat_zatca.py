"""VAT totals aligned with ZATCA Sales & Purchase report (Option A), plus not-submitted tracking."""

from __future__ import annotations

import importlib
import json
from datetime import date
from typing import Any, Optional

import frappe
from frappe.utils import getdate

from erp_analysis.permissions.access_profile import si_territory_sql

ZATCA_SUBMITTED_STATUSES = frozenset({"CLEARED", "REPORTED"})

MONTH_LABELS = (
	"Jan",
	"Feb",
	"Mar",
	"Apr",
	"May",
	"Jun",
	"Jul",
	"Aug",
	"Sep",
	"Oct",
	"Nov",
	"Dec",
)

VAT_DRILL_BUCKETS = frozenset(
	{
		"not_submitted.sales.draft",
		"not_submitted.sales.zatca_pending",
		"not_submitted.purchase.draft",
		"not_submitted.purchase.cancelled",
	}
)


def _zatca_vat_report_module():
	return importlib.import_module(
		"zatca_erpgulf.zatca_erpgulf.report.vat_report_zatca_on_sales_&_purchase."
		"vat_report_zatca_on_sales_&_purchase"
	)


def si_territory_named_sql(
	territories: Optional[list[str]],
	field: str = "si.territory",
	prefix: str = "vat_terr",
) -> tuple[str, dict[str, Any]]:
	"""Named-parameter territory fragment for ZATCA queries (uses %(key)s placeholders)."""
	if not territories:
		return "", {}
	if len(territories) == 1:
		key = f"{prefix}_0"
		return f" AND {field} = %({key})s ", {key: territories[0]}
	extra: dict[str, Any] = {}
	placeholders: list[str] = []
	for i, terr in enumerate(territories):
		key = f"{prefix}_{i}"
		extra[key] = terr
		placeholders.append(f"%({key})s")
	return f" AND {field} IN ({', '.join(placeholders)}) ", extra


def get_sales_vat_totals_zatca(
	filters: dict[str, Any],
	territories: Optional[list[str]] = None,
) -> dict[str, dict[str, float]]:
	"""Same logic as desk report; optional SI territory filter."""
	mod = _zatca_vat_report_module()
	filters = dict(filters or {})
	orig_build = mod.build_filters_sql

	def build_filters_sql_patched(f, table_alias="si"):
		where = orig_build(f, table_alias)
		if table_alias == "si" and territories:
			frag, named = si_territory_named_sql(territories, field=f"{table_alias}.territory")
			filters.update(named)
			return where + frag
		return where

	mod.build_filters_sql = build_filters_sql_patched
	try:
		return mod.get_sales_vat_totals_sql(filters)
	except ImportError:
		frappe.throw("ZATCA app (zatca_erpgulf) is required for VAT dashboard.")
	finally:
		mod.build_filters_sql = orig_build


def get_purchase_vat_totals_zatca(filters: dict[str, Any]) -> dict[str, dict[str, float]]:
	mod = _zatca_vat_report_module()
	try:
		return mod.get_purchase_vat_totals_sql(dict(filters or {}))
	except ImportError:
		frappe.throw("ZATCA app (zatca_erpgulf) is required for VAT dashboard.")


def _round_totals(totals: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]:
	out: dict[str, dict[str, float]] = {}
	for cat, bucket in totals.items():
		out[cat] = {
			"amount": round(float(bucket.get("amount") or 0), 2),
			"adjustment": round(float(bucket.get("adjustment") or 0), 2),
			"vat": round(float(bucket.get("vat") or 0), 2),
		}
	return out


def _sum_vat(totals: dict[str, dict[str, float]]) -> float:
	return round(sum(float(v.get("vat") or 0) for v in totals.values()), 2)


def _invoice_bucket(
	company: Optional[str],
	from_date,
	to_date,
	*,
	docstatus: int,
	territories: Optional[list[str]] = None,
	zatca_pending_only: bool = False,
) -> dict[str, Any]:
	params: list[Any] = [from_date, to_date, docstatus]
	company_sql = ""
	if company:
		company_sql = " AND company = %s"
		params.append(company)
	terr_sql, terr_params = si_territory_sql(territories, field="territory")
	params.extend(terr_params)

	zatca_sql = ""
	if zatca_pending_only:
		zatca_sql = """
		  AND (
		    COALESCE(custom_zatca_status, '') = ''
		    OR custom_zatca_status NOT IN ('CLEARED', 'REPORTED')
		  )
		"""

	row = frappe.db.sql(
		f"""
		SELECT
		  COUNT(*) AS cnt,
		  COALESCE(SUM(base_net_total), 0) AS net_total,
		  COALESCE(SUM(base_total_taxes_and_charges), 0) AS vat
		FROM `tabSales Invoice`
		WHERE posting_date BETWEEN %s AND %s
		  AND docstatus = %s
		  {company_sql}
		  {terr_sql}
		  {zatca_sql}
		""",
		tuple(params),
		as_dict=True,
	)[0]
	return {
		"count": int(row.cnt or 0),
		"net_total": round(float(row.net_total or 0), 2),
		"vat": round(float(row.vat or 0), 2),
	}


def _zatca_error_from_response(status: str | None, full_response: str | None) -> str:
	status = (status or "").strip()
	if status in ZATCA_SUBMITTED_STATUSES:
		return ""
	raw = (full_response or "").strip()
	if not raw or raw == "Not Submitted":
		return ""
	if raw.startswith("{"):
		try:
			parsed = json.loads(raw)
			for key in ("message", "error", "errorMessage", "validationResults", "detail"):
				val = parsed.get(key)
				if isinstance(val, str) and val.strip():
					return val.strip()[:2000]
				if val is not None and key != "validationResults":
					return str(val)[:2000]
		except json.JSONDecodeError:
			pass
	return raw[:2000]


def _monthly_output_vat(
	company: Optional[str],
	year: int,
	territories: Optional[list[str]] = None,
) -> list[float]:
	params: list[Any] = [f"{year}-01-01", f"{year}-12-31"]
	company_sql = ""
	if company:
		company_sql = " AND company = %s"
		params.append(company)
	terr_sql, terr_params = si_territory_sql(territories, field="territory")
	params.extend(terr_params)

	rows = frappe.db.sql(
		f"""
		SELECT MONTH(posting_date) AS month_num,
		       COALESCE(SUM(base_total_taxes_and_charges), 0) AS vat
		FROM `tabSales Invoice`
		WHERE docstatus = 1
		  AND posting_date BETWEEN %s AND %s
		  {company_sql}
		  {terr_sql}
		GROUP BY MONTH(posting_date)
		""",
		tuple(params),
		as_dict=True,
	)
	by_month = {int(r.month_num): float(r.vat or 0) for r in rows}
	return [round(by_month.get(m, 0.0), 2) for m in range(1, 13)]


def _monthly_input_vat(company: Optional[str], year: int) -> list[float]:
	params: list[Any] = [f"{year}-01-01", f"{year}-12-31"]
	company_sql = ""
	if company:
		company_sql = " AND company = %s"
		params.append(company)

	rows = frappe.db.sql(
		f"""
		SELECT MONTH(posting_date) AS month_num,
		       COALESCE(SUM(base_total_taxes_and_charges), 0) AS vat
		FROM `tabPurchase Invoice`
		WHERE docstatus = 1
		  AND posting_date BETWEEN %s AND %s
		  {company_sql}
		GROUP BY MONTH(posting_date)
		""",
		tuple(params),
		as_dict=True,
	)
	by_month = {int(r.month_num): float(r.vat or 0) for r in rows}
	return [round(by_month.get(m, 0.0), 2) for m in range(1, 13)]


def build_monthly_trend(
	company: Optional[str],
	to_date: date,
	territories: Optional[list[str]] = None,
) -> dict[str, Any]:
	"""Calendar-year output/input VAT by month (current vs previous year)."""
	end = getdate(to_date)
	current_year = end.year
	previous_year = current_year - 1
	out_cur = _monthly_output_vat(company, current_year, territories)
	out_prev = _monthly_output_vat(company, previous_year, territories)
	in_cur = _monthly_input_vat(company, current_year)
	in_prev = _monthly_input_vat(company, previous_year)
	net_cur = [round(o - i, 2) for o, i in zip(out_cur, in_cur)]
	net_prev = [round(o - i, 2) for o, i in zip(out_prev, in_prev)]
	return {
		"labels": list(MONTH_LABELS),
		"output_vat": {"current": out_cur, "previous": out_prev},
		"input_vat": {"current": in_cur, "previous": in_prev},
		"net_vat": {"current": net_cur, "previous": net_prev},
		"years": {"current": current_year, "previous": previous_year},
	}


def _fetch_sales_invoice_documents(
	company: Optional[str],
	from_date,
	to_date,
	*,
	docstatus: int,
	territories: Optional[list[str]] = None,
	zatca_pending_only: bool = False,
	limit: int = 500,
) -> list[dict[str, Any]]:
	params: list[Any] = [from_date, to_date, docstatus]
	company_sql = ""
	if company:
		company_sql = " AND si.company = %s"
		params.append(company)
	terr_sql, terr_params = si_territory_sql(territories, field="si.territory")
	params.extend(terr_params)

	zatca_sql = ""
	if zatca_pending_only:
		zatca_sql = """
		  AND (
		    COALESCE(si.custom_zatca_status, '') = ''
		    OR si.custom_zatca_status NOT IN ('CLEARED', 'REPORTED')
		  )
		"""

	params.append(limit)
	rows = frappe.db.sql(
		f"""
		SELECT
		  si.name,
		  si.customer_name,
		  si.territory,
		  si.posting_date,
		  si.docstatus,
		  COALESCE(si.base_grand_total, 0) AS base_grand_total,
		  COALESCE(si.base_net_total, 0) AS base_net_total,
		  COALESCE(si.base_total_taxes_and_charges, 0) AS base_total_taxes_and_charges,
		  si.custom_zatca_status,
		  si.custom_zatca_full_response
		FROM `tabSales Invoice` si
		WHERE si.posting_date BETWEEN %s AND %s
		  AND si.docstatus = %s
		  {company_sql}
		  {terr_sql}
		  {zatca_sql}
		ORDER BY si.posting_date DESC, si.name DESC
		LIMIT %s
		""",
		tuple(params),
		as_dict=True,
	)
	out: list[dict[str, Any]] = []
	for r in rows:
		status = (r.custom_zatca_status or "").strip() or "Not Submitted"
		out.append(
			{
				"name": r.name,
				"doctype": "Sales Invoice",
				"customer_name": r.customer_name,
				"party": r.customer_name,
				"territory": r.territory,
				"posting_date": str(r.posting_date),
				"grand_total": round(float(r.base_grand_total or 0), 2),
				"net_total": round(float(r.base_net_total or 0), 2),
				"taxable_amount": round(float(r.base_net_total or 0), 2),
				"vat_amount": round(float(r.base_total_taxes_and_charges or 0), 2),
				"zatca_status": status,
				"zatca_error": _zatca_error_from_response(status, r.custom_zatca_full_response),
				"docstatus": int(r.docstatus or 0),
			}
		)
	return out


def _fetch_purchase_invoice_documents(
	company: Optional[str],
	from_date,
	to_date,
	*,
	docstatus: int,
	limit: int = 500,
) -> list[dict[str, Any]]:
	params: list[Any] = [from_date, to_date, docstatus]
	company_sql = ""
	if company:
		company_sql = " AND pi.company = %s"
		params.append(company)
	params.append(limit)

	rows = frappe.db.sql(
		f"""
		SELECT
		  pi.name,
		  pi.supplier_name,
		  pi.posting_date,
		  pi.docstatus,
		  COALESCE(pi.base_grand_total, 0) AS base_grand_total,
		  COALESCE(pi.base_net_total, 0) AS base_net_total,
		  COALESCE(pi.base_total_taxes_and_charges, 0) AS base_total_taxes_and_charges
		FROM `tabPurchase Invoice` pi
		WHERE pi.posting_date BETWEEN %s AND %s
		  AND pi.docstatus = %s
		  {company_sql}
		ORDER BY pi.posting_date DESC, pi.name DESC
		LIMIT %s
		""",
		tuple(params),
		as_dict=True,
	)
	out: list[dict[str, Any]] = []
	for r in rows:
		out.append(
			{
				"name": r.name,
				"doctype": "Purchase Invoice",
				"supplier_name": r.supplier_name,
				"party": r.supplier_name,
				"customer_name": r.supplier_name,
				"territory": None,
				"posting_date": str(r.posting_date),
				"grand_total": round(float(r.base_grand_total or 0), 2),
				"net_total": round(float(r.base_net_total or 0), 2),
				"taxable_amount": round(float(r.base_net_total or 0), 2),
				"vat_amount": round(float(r.base_total_taxes_and_charges or 0), 2),
				"zatca_status": None,
				"zatca_error": "",
				"docstatus": int(r.docstatus or 0),
			}
		)
	return out


def _documents_for_bucket(
	bucket_key: str,
	company: Optional[str],
	from_date,
	to_date,
	territories: Optional[list[str]],
	limit: int,
) -> list[dict[str, Any]]:
	if bucket_key == "not_submitted.sales.draft":
		return _fetch_sales_invoice_documents(
			company, from_date, to_date, docstatus=0, territories=territories, limit=limit
		)
	if bucket_key == "not_submitted.sales.zatca_pending":
		return _fetch_sales_invoice_documents(
			company,
			from_date,
			to_date,
			docstatus=1,
			territories=territories,
			zatca_pending_only=True,
			limit=limit,
		)
	if bucket_key == "not_submitted.purchase.draft":
		return _fetch_purchase_invoice_documents(
			company, from_date, to_date, docstatus=0, limit=limit
		)
	if bucket_key == "not_submitted.purchase.cancelled":
		return _fetch_purchase_invoice_documents(
			company, from_date, to_date, docstatus=2, limit=limit
		)
	frappe.throw(f"Unknown VAT bucket_key: {bucket_key}")


def _attach_documents_to_bucket(bucket: dict[str, Any], invoices: list[dict[str, Any]]) -> None:
	bucket["invoices"] = invoices
	bucket["documents"] = invoices
	if invoices and (invoices[0].get("doctype") or "") == "Sales Invoice":
		bucket["sales_invoices"] = invoices


def _purchase_bucket(
	company: Optional[str],
	from_date,
	to_date,
	*,
	docstatus: int,
) -> dict[str, Any]:
	params: list[Any] = [from_date, to_date, docstatus]
	company_sql = ""
	if company:
		company_sql = " AND company = %s"
		params.append(company)

	row = frappe.db.sql(
		f"""
		SELECT
		  COUNT(*) AS cnt,
		  COALESCE(SUM(base_net_total), 0) AS net_total,
		  COALESCE(SUM(base_total_taxes_and_charges), 0) AS vat
		FROM `tabPurchase Invoice`
		WHERE posting_date BETWEEN %s AND %s
		  AND docstatus = %s
		  {company_sql}
		""",
		tuple(params),
		as_dict=True,
	)[0]
	return {
		"count": int(row.cnt or 0),
		"net_total": round(float(row.net_total or 0), 2),
		"vat": round(float(row.vat or 0), 2),
	}


def get_vat_dashboard_payload(
	*,
	company: Optional[str],
	from_date,
	to_date,
	period_key: str,
	territories: Optional[list[str]] = None,
	include_documents: bool = False,
	bucket_key: Optional[str] = None,
	document_limit: int = 500,
) -> dict[str, Any]:
	if bucket_key and bucket_key not in VAT_DRILL_BUCKETS:
		frappe.throw(f"Unsupported bucket_key. Allowed: {', '.join(sorted(VAT_DRILL_BUCKETS))}")
	filters: dict[str, Any] = {
		"from_date": from_date,
		"to_date": to_date,
	}
	if company:
		filters["company"] = company

	sales_totals = _round_totals(get_sales_vat_totals_zatca(filters, territories=territories))
	purchase_totals = _round_totals(get_purchase_vat_totals_zatca(filters))
	total_sales_vat = _sum_vat(sales_totals)
	total_purchase_vat = _sum_vat(purchase_totals)

	monthly_trend = build_monthly_trend(company, getdate(to_date), territories)

	not_submitted = {
		"sales": {
			"draft": _invoice_bucket(
				company, from_date, to_date, docstatus=0, territories=territories
			),
			"zatca_pending": _invoice_bucket(
				company,
				from_date,
				to_date,
				docstatus=1,
				territories=territories,
				zatca_pending_only=True,
			),
		},
		"purchase": {
			"draft": _purchase_bucket(company, from_date, to_date, docstatus=0),
			"cancelled": _purchase_bucket(company, from_date, to_date, docstatus=2),
		},
	}

	per_bucket_limit = min(max(int(document_limit or 500), 1), 2000)
	summary_doc_cap = 50 if include_documents and not bucket_key else per_bucket_limit
	drill_docs: list[dict[str, Any]] | None = None

	if bucket_key:
		drill_docs = _documents_for_bucket(
			bucket_key, company, from_date, to_date, territories, per_bucket_limit
		)
		if bucket_key.startswith("not_submitted.sales."):
			sub = bucket_key.split(".")[-1]
			_attach_documents_to_bucket(not_submitted["sales"][sub], drill_docs)
		else:
			sub = bucket_key.split(".")[-1]
			_attach_documents_to_bucket(not_submitted["purchase"][sub], drill_docs)
	elif include_documents:
		for key in VAT_DRILL_BUCKETS:
			docs = _documents_for_bucket(
				key, company, from_date, to_date, territories, summary_doc_cap
			)
			if key.startswith("not_submitted.sales."):
				sub = key.split(".")[-1]
				_attach_documents_to_bucket(not_submitted["sales"][sub], docs)
			else:
				sub = key.split(".")[-1]
				_attach_documents_to_bucket(not_submitted["purchase"][sub], docs)

	payload = {
		"period": {
			"from_date": str(from_date),
			"to_date": str(to_date),
			"key": period_key,
		},
		"company": company,
		"meta": {
			"source": "zatca_vat_report_on_sales_and_purchase",
			"territory_filter": territories,
			"territory_applied_to": {
				"sales_output_vat": bool(territories),
				"purchase_input_vat": False,
			},
			"submitted_definition": "Posted invoices (docstatus=1); ZATCA category logic from desk report.",
			"not_submitted_definition": (
				"Draft SI/PI (docstatus=0); posted SI with ZATCA status other than CLEARED/REPORTED; "
				"cancelled PI (docstatus=2) listed separately."
			),
			"monthly_trend_definition": (
				"Calendar-year posted invoice header VAT (docstatus=1); output respects territory, input company-wide."
			),
			"drill_buckets": sorted(VAT_DRILL_BUCKETS),
		},
		"submitted": {
			"sales": {
				"categories": sales_totals,
				"total_vat": total_sales_vat,
			},
			"purchase": {
				"categories": purchase_totals,
				"total_vat": total_purchase_vat,
			},
			"net_vat_due": round(total_sales_vat - total_purchase_vat, 2),
		},
		"not_submitted": not_submitted,
		"monthly_trend": monthly_trend,
		"vat_monthly_trend": monthly_trend,
		"trends": {"monthly": monthly_trend},
	}
	if bucket_key and drill_docs is not None:
		payload["bucket_key"] = bucket_key
		payload["drill"] = {
			"bucket_key": bucket_key,
			"invoices": drill_docs,
			"documents": drill_docs,
		}
	return payload
