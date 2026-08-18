"""Receivables attention alerts for mobile dashboard."""

from __future__ import annotations

from typing import Any, Optional

import frappe

from erp_analysis.permissions.access_profile import resolve_territory_scope, si_territory_sql


def get_receivables_attention_items(
	company: Optional[str] = None,
	limit: int = 10,
) -> dict[str, Any]:
	company = company or frappe.defaults.get_user_default("Company")
	limit = max(1, min(int(limit or 10), 50))
	scope = resolve_territory_scope(company=company, module="receivables")
	terr_sql, terr_params = si_territory_sql(scope, field="si.territory")
	base = (company,) + tuple(terr_params)

	credit_limit_count = int(
		frappe.db.sql(
			f"""
			SELECT COUNT(DISTINCT si.customer)
			FROM `tabSales Invoice` si
			INNER JOIN `tabCustomer` c ON c.name = si.customer
			WHERE si.docstatus = 1 AND si.outstanding_amount > 0 AND si.company = %s
			  AND c.credit_limit > 0 AND si.outstanding_amount > c.credit_limit
			  {terr_sql}
			""",
			base,
		)[0][0]
		or 0
	)

	overdue_60 = int(
		frappe.db.sql(
			f"""
			SELECT COUNT(*)
			FROM `tabSales Invoice` si
			WHERE si.docstatus = 1 AND si.outstanding_amount > 0
			  AND si.due_date < DATE_SUB(CURDATE(), INTERVAL 60 DAY)
			  AND si.company = %s
			  {terr_sql}
			""",
			base,
		)[0][0]
		or 0
	)

	overdue_90 = int(
		frappe.db.sql(
			f"""
			SELECT COUNT(*)
			FROM `tabSales Invoice` si
			WHERE si.docstatus = 1 AND si.outstanding_amount > 0
			  AND si.due_date < DATE_SUB(CURDATE(), INTERVAL 90 DAY)
			  AND si.company = %s
			  {terr_sql}
			""",
			base,
		)[0][0]
		or 0
	)

	unallocated = int(
		frappe.db.sql(
			f"""
			SELECT COUNT(*)
			FROM `tabPayment Entry` pe
			WHERE pe.docstatus = 1 AND pe.payment_type = 'Receive'
			  AND pe.company = %s AND pe.unallocated_amount > 0
			""",
			(company,),
		)[0][0]
		or 0
	)

	items = []
	if credit_limit_count:
		items.append(
			{
				"key": "credit_limit",
				"label": "Customers Over Credit Limit",
				"count": credit_limit_count,
				"severity": "warning",
			}
		)
	if overdue_60:
		items.append(
			{
				"key": "overdue_60",
				"label": "Invoices Overdue > 60 Days",
				"count": overdue_60,
				"severity": "warning",
			}
		)
	if overdue_90:
		items.append(
			{
				"key": "overdue_90",
				"label": "Invoices Overdue > 90 Days",
				"count": overdue_90,
				"severity": "danger",
			}
		)
	if unallocated:
		items.append(
			{
				"key": "unallocated_payments",
				"label": "Unallocated Payments",
				"count": unallocated,
				"severity": "warning",
			}
		)

	return {
		"items": items[:limit],
		"meta": {"schema_version": 1, "count": len(items)},
	}
