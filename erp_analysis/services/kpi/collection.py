"""Collection actuals — Payment Entry received amounts (not AR outstanding)."""

from __future__ import annotations

from datetime import date
from typing import Any, List, Optional

import frappe
from frappe.utils import get_first_day, getdate, nowdate

from erp_analysis.permissions.access_profile import resolve_territory_scope, si_territory_sql


def _sum_received(
	company: Optional[str],
	from_date: date,
	to_date: date,
	territories: Optional[List[str]] = None,
) -> float:
	params: list[Any] = [from_date, to_date]
	company_sql = ""
	if company:
		company_sql = " AND pe.company = %s"
		params.append(company)

	# Profile users: only receipts for customers in allowed territories
	party_join = ""
	terr_sql = ""
	if territories:
		party_join = """
			INNER JOIN `tabCustomer` c
				ON c.name = pe.party AND pe.party_type = 'Customer'
		"""
		terr_sql, terr_params = si_territory_sql(territories, field="c.territory")
		params.extend(terr_params)

	row = frappe.db.sql(
		f"""
		SELECT COALESCE(SUM(pe.base_paid_amount), 0) AS collected
		FROM `tabPayment Entry` pe
		{party_join}
		WHERE pe.docstatus = 1
		  AND pe.payment_type = 'Receive'
		  AND pe.posting_date BETWEEN %s AND %s
		  {company_sql}
		  {terr_sql}
		""",
		tuple(params),
		as_dict=True,
	)[0]
	return float(row.collected or 0)


def get_collection_period_kpis(
	company: Optional[str] = None,
	as_of: Optional[str] = None,
	territory: Optional[str] = None,
	territories: Optional[List[str]] = None,
) -> dict[str, Any]:
	today = getdate(as_of or nowdate())
	mtd_start = get_first_day(today)
	ytd_start = date(today.year, 1, 1)
	if territories is not None:
		scope = territories
	else:
		scope = resolve_territory_scope(
			requested=territory, company=company, purpose="view", module="sales"
		)

	return {
		"today": round(_sum_received(company, today, today, scope), 2),
		"mtd": round(_sum_received(company, mtd_start, today, scope), 2),
		"ytd": round(_sum_received(company, ytd_start, today, scope), 2),
	}
