import json

import frappe

from erp_analysis.services.analytics_dimensions import parse_logical_filters, validate_logical_filters
from erp_analysis.services.sales_period import resolve_period_dates
from erp_analysis.services.analytics_sales import (
	_query_dashboard_profit_totals,
	get_sales_kpi,
)


def main():
	user = "sakeer@printechs.com"
	company = "Printechs Advanced Printing Trading Co."
	frappe.set_user(user)
	filters = json.dumps({"territory": ["Dammam"]})
	parsed = parse_logical_filters(filters)
	validated = validate_logical_filters(user, company, parsed)
	start, end, _ = resolve_period_dates(None, None, period="ytd")
	print("dashboard totals", _query_dashboard_profit_totals(user, company, start, end, validated))
	for metric in ("net_sales", "cogs", "gross_profit", "gp_pct"):
		k = get_sales_kpi(user=user, company=company, metric=metric, period="ytd", filters=filters)
		print(metric, k["value"])
