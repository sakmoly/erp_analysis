import json

import frappe

from erp_analysis.services.mobile_widgets import (
	_uses_filter_aware_sales_kpi,
	resolve_widget_definition,
	_kpi_widget_payload,
)


def main():
	user = "sakeer@printechs.com"
	company = "Printechs Advanced Printing Trading Co."
	frappe.set_user(user)
	w = resolve_widget_definition(user, "sales_gp_kpi", company=company)
	print("widget dashboard_id", w.get("dashboard_id"), "metric", w.get("metric_key"))
	filters = json.dumps({"territory": ["Dammam"]})
	print("uses analytics", _uses_filter_aware_sales_kpi(w, w.get("metric_key") or "", filters))
	filters = json.dumps({"territory": ["Dammam"]})
	out = _kpi_widget_payload(
		user,
		company,
		w,
		from_date=None,
		to_date=None,
		filters=filters,
		compare_override="ly",
	)
	print("value", out.get("value"), "meta period", (out.get("meta") or {}).get("period"))
