import json

import frappe

from erp_analysis.services.sales_period import resolve_period_dates
from erp_analysis.services.vat_zatca import get_vat_dashboard_payload


def main():
	frappe.set_user("Administrator")
	company = "Printechs Advanced Printing Trading Co."
	start, end, key = resolve_period_dates(None, None, period="ytd")
	payload = get_vat_dashboard_payload(
		company=company,
		from_date=start,
		to_date=end,
		period_key=key,
		territories=["Dammam"],
	)
	print(
		json.dumps(
			{
				"net_vat_due": payload["submitted"]["net_vat_due"],
				"sales_vat": payload["submitted"]["sales"]["total_vat"],
				"purchase_vat": payload["submitted"]["purchase"]["total_vat"],
				"not_submitted": payload["not_submitted"],
			},
			indent=2,
		)
	)
