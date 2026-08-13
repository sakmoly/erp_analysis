"""Collection dashboard breakdowns and attention lists (Payment Entry actuals)."""

from __future__ import annotations

from datetime import date
from typing import Any, List, Optional

import frappe
from frappe.utils import get_first_day, getdate, nowdate

from erp_analysis.permissions.access_profile import resolve_territory_scope, si_territory_sql
from erp_analysis.services.kpi.collection import get_collection_period_kpis


def _period_bounds(
	from_date: Optional[str] = None,
	to_date: Optional[str] = None,
) -> tuple[date, date]:
	end = getdate(to_date or nowdate())
	start = getdate(from_date) if from_date else get_first_day(end)
	return start, end


def _company_sql(company: Optional[str], alias: str = "pe") -> tuple[str, list[Any]]:
	if not company:
		return "", []
	return f" AND {alias}.company = %s", [company]


def _customer_territory_sql(
	territories: Optional[List[str]],
	alias: str = "c",
) -> tuple[str, list[Any]]:
	return si_territory_sql(territories, field=f"{alias}.territory")


def get_collection_by_territory(
	company: Optional[str] = None,
	from_date: Optional[str] = None,
	to_date: Optional[str] = None,
	limit: int = 20,
	territories: Optional[List[str]] = None,
) -> list[dict[str, Any]]:
	start, end = _period_bounds(from_date, to_date)
	company_sql, company_params = _company_sql(company)
	terr_sql, terr_params = _customer_territory_sql(territories)

	rows = frappe.db.sql(
		f"""
		SELECT
			COALESCE(c.territory, 'Unassigned') AS territory,
			COALESCE(SUM(per.allocated_amount), 0) AS collected,
			COUNT(DISTINCT pe.name) AS payment_count
		FROM `tabPayment Entry` pe
		INNER JOIN `tabPayment Entry Reference` per ON per.parent = pe.name
		LEFT JOIN `tabCustomer` c ON c.name = pe.party AND pe.party_type = 'Customer'
		WHERE pe.docstatus = 1
		  AND pe.payment_type = 'Receive'
		  AND pe.posting_date BETWEEN %s AND %s
		  {company_sql}
		  {terr_sql}
		GROUP BY COALESCE(c.territory, 'Unassigned')
		ORDER BY collected DESC
		LIMIT %s
		""",
		tuple([start, end, *company_params, *terr_params, int(limit)]),
		as_dict=True,
	)

	return [
		{
			"territory": row.territory,
			"collected": round(float(row.collected or 0), 2),
			"payment_count": int(row.payment_count or 0),
		}
		for row in rows
	]


def get_collection_by_customer(
	company: Optional[str] = None,
	from_date: Optional[str] = None,
	to_date: Optional[str] = None,
	territory: Optional[str] = None,
	limit: int = 20,
	territories: Optional[List[str]] = None,
) -> list[dict[str, Any]]:
	start, end = _period_bounds(from_date, to_date)
	company_sql, company_params = _company_sql(company)
	territory_sql = ""
	territory_params: list[Any] = []
	if territory:
		territory_sql = " AND c.territory = %s"
		territory_params.append(territory)
	elif territories:
		terr_sql, terr_params = _customer_territory_sql(territories)
		territory_sql = terr_sql
		territory_params.extend(terr_params)

	rows = frappe.db.sql(
		f"""
		SELECT
			pe.party AS customer,
			COALESCE(c.customer_name, pe.party) AS customer_name,
			COALESCE(c.territory, '') AS territory,
			COALESCE(SUM(per.allocated_amount), 0) AS collected,
			COUNT(DISTINCT pe.name) AS payment_count
		FROM `tabPayment Entry` pe
		INNER JOIN `tabPayment Entry Reference` per ON per.parent = pe.name
		LEFT JOIN `tabCustomer` c ON c.name = pe.party AND pe.party_type = 'Customer'
		WHERE pe.docstatus = 1
		  AND pe.payment_type = 'Receive'
		  AND pe.party_type = 'Customer'
		  AND pe.posting_date BETWEEN %s AND %s
		  {company_sql}
		  {territory_sql}
		GROUP BY pe.party, c.customer_name, c.territory
		ORDER BY collected DESC
		LIMIT %s
		""",
		tuple([start, end, *company_params, *territory_params, int(limit)]),
		as_dict=True,
	)

	return [
		{
			"customer": row.customer,
			"customer_name": row.customer_name,
			"territory": row.territory,
			"collected": round(float(row.collected or 0), 2),
			"payment_count": int(row.payment_count or 0),
		}
		for row in rows
	]


def get_collection_dashboard_payload(
	company: Optional[str] = None,
	from_date: Optional[str] = None,
	to_date: Optional[str] = None,
	territory: Optional[str] = None,
	limit: int = 20,
	territories: Optional[List[str]] = None,
) -> dict[str, Any]:
	start, end = _period_bounds(from_date, to_date)
	if territories is None:
		territories = resolve_territory_scope(
			requested=territory, company=company, purpose="view", module="sales"
		)
	return {
		"kpis": get_collection_period_kpis(
			company=company, as_of=end, territory=territory, territories=territories
		),
		"period": {"from_date": str(start), "to_date": str(end)},
		"by_territory": get_collection_by_territory(
			company=company, from_date=start, to_date=end, limit=limit, territories=territories
		),
		"by_customer": get_collection_by_customer(
			company=company,
			from_date=start,
			to_date=end,
			territory=territory,
			limit=limit,
			territories=territories if not territory else None,
		),
	}


def get_overdue_customers(
	company: Optional[str] = None,
	limit: int = 20,
	territories: Optional[List[str]] = None,
) -> list[dict[str, Any]]:
	company = company or frappe.defaults.get_user_default("Company")
	if not company:
		return []

	terr_sql, terr_params = si_territory_sql(territories, field="si.territory")

	rows = frappe.db.sql(
		f"""
		SELECT
			si.customer AS customer,
			COALESCE(c.customer_name, si.customer) AS customer_name,
			COALESCE(c.territory, '') AS territory,
			COALESCE(SUM(si.outstanding_amount), 0) AS total_outstanding,
			COALESCE(SUM(
				CASE WHEN si.due_date < CURDATE() THEN si.outstanding_amount ELSE 0 END
			), 0) AS overdue,
			MIN(CASE WHEN si.due_date < CURDATE() THEN si.due_date END) AS oldest_due_date
		FROM `tabSales Invoice` si
		LEFT JOIN `tabCustomer` c ON c.name = si.customer
		WHERE si.docstatus = 1
		  AND si.outstanding_amount > 0
		  AND si.company = %s
		  {terr_sql}
		GROUP BY si.customer, c.customer_name, c.territory
		HAVING overdue > 0
		ORDER BY overdue DESC
		LIMIT %s
		""",
		(company, *terr_params, int(limit)),
		as_dict=True,
	)

	return [
		{
			"customer": row.customer,
			"customer_name": row.customer_name,
			"territory": row.territory,
			"overdue": round(float(row.overdue or 0), 2),
			"total_outstanding": round(float(row.total_outstanding or 0), 2),
			"oldest_due_date": str(row.oldest_due_date) if row.oldest_due_date else None,
		}
		for row in rows
	]


def get_unallocated_payments(
	company: Optional[str] = None,
	min_unallocated: float = 100.0,
	limit: int = 20,
	territories: Optional[List[str]] = None,
) -> list[dict[str, Any]]:
	company = company or frappe.defaults.get_user_default("Company")
	if not company:
		return []

	party_join = ""
	terr_sql = ""
	terr_params: list[Any] = []
	if territories:
		party_join = """
			INNER JOIN `tabCustomer` c
				ON c.name = pe.party AND pe.party_type = 'Customer'
		"""
		terr_sql, terr_params = _customer_territory_sql(territories)

	rows = frappe.db.sql(
		f"""
		SELECT
			pe.name AS payment_entry,
			pe.party,
			pe.posting_date,
			COALESCE(pe.base_paid_amount, 0) AS paid_amount,
			COALESCE(pe.unallocated_amount, 0) AS unallocated_amount
		FROM `tabPayment Entry` pe
		{party_join}
		WHERE pe.docstatus = 1
		  AND pe.payment_type = 'Receive'
		  AND pe.party_type = 'Customer'
		  AND pe.company = %s
		  AND pe.unallocated_amount >= %s
		  {terr_sql}
		ORDER BY pe.unallocated_amount DESC
		LIMIT %s
		""",
		(company, float(min_unallocated), *terr_params, int(limit)),
		as_dict=True,
	)

	return [
		{
			"payment_entry": row.payment_entry,
			"party": row.party,
			"posting_date": str(row.posting_date),
			"paid_amount": round(float(row.paid_amount or 0), 2),
			"unallocated_amount": round(float(row.unallocated_amount or 0), 2),
		}
		for row in rows
	]


def get_collection_attention_payload(
	company: Optional[str] = None,
	min_unallocated: float = 100.0,
	limit: int = 20,
	territories: Optional[List[str]] = None,
) -> dict[str, Any]:
	if territories is None:
		territories = resolve_territory_scope(company=company, purpose="view", module="receivables")
	return {
		"overdue_customers": get_overdue_customers(company=company, limit=limit, territories=territories),
		"unallocated_payments": get_unallocated_payments(
			company=company, min_unallocated=min_unallocated, limit=limit, territories=territories
		),
	}
