import frappe


def main():
	doc = frappe.get_doc("Mobile App Profile", "PRINTECHS-B2B")
	for row in sorted(doc.dashboard_widgets or [], key=lambda r: r.sort_order or 0):
		key = (row.widget_key or "").strip()
		board = (row.dashboard_id or "").strip()
		if board != "sales_overview":
			continue
		print(key, row.metric_key, row.period, row.enabled)
