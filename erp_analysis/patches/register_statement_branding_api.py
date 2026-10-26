"""Register get_statement_branding for mobile SOA PDF fallback."""

from __future__ import annotations

import frappe

OBJECT_KEYS = (
	("erp_analysis.customer_notifications.get_statement_branding", "SOA Branding (mobile)"),
	("erp_analysis.receivables.get_statement_branding", "SOA Branding (receivables alias)"),
)


def execute():
	for object_key, label in OBJECT_KEYS:
		if frappe.db.exists("Access Object Registry", {"object_key": object_key}):
			continue
		frappe.get_doc(
			{
				"doctype": "Access Object Registry",
				"object_type": "API",
				"object_key": object_key,
				"label": label,
				"is_active": 1,
			}
		).insert(ignore_permissions=True)
	frappe.db.commit()
