"""Receivables summary KPIs for executive dashboard."""

from __future__ import annotations

from typing import Any, List, Optional

import frappe

from erp_analysis.permissions.access_profile import resolve_territory_scope, si_territory_sql


def get_receivables_summary_kpis(
	company: Optional[str] = None,
	territory: Optional[str] = None,
	territories: Optional[List[str]] = None,
) -> dict[str, Any]:
	company = company or frappe.defaults.get_user_default("Company")
	if not company:
		return {"total": 0, "overdue": 0, "overdue_pct": 0}

	if territories is not None:
		scope = territories
	else:
		scope = resolve_territory_scope(
			requested=territory,
			company=company,
			purpose="view",
			module="receivables",
		)
	terr_sql, terr_params = si_territory_sql(scope, field="territory")

	total = float(
		frappe.db.sql(
			f"""
			SELECT COALESCE(SUM(outstanding_amount), 0)
			FROM `tabSales Invoice`
			WHERE docstatus = 1
			  AND outstanding_amount > 0
			  AND company = %s
			  {terr_sql}
			""",
			tuple([company] + terr_params),
		)[0][0]
		or 0
	)

	overdue = float(
		frappe.db.sql(
			f"""
			SELECT COALESCE(SUM(outstanding_amount), 0)
			FROM `tabSales Invoice`
			WHERE docstatus = 1
			  AND outstanding_amount > 0
			  AND due_date < CURDATE()
			  AND company = %s
			  {terr_sql}
			""",
			tuple([company] + terr_params),
		)[0][0]
		or 0
	)

	overdue_pct = round(overdue / total * 100, 2) if total > 0 else 0.0

	return {
		"total": round(total, 2),
		"overdue": round(overdue, 2),
		"overdue_pct": overdue_pct,
	}
