"""Register mobile VAT dashboard API (ZATCA-aligned)."""

from __future__ import annotations

import frappe

from erp_analysis.tax import VAT_API_OBJECT

LABEL = "VAT Dashboard (ZATCA output + input)"


def execute():
	if not frappe.db.exists("Access Object Registry", {"object_key": VAT_API_OBJECT}):
		frappe.get_doc(
			{
				"doctype": "Access Object Registry",
				"object_type": "API",
				"object_key": VAT_API_OBJECT,
				"label": LABEL,
				"is_active": 1,
			}
		).insert(ignore_permissions=True)
	frappe.db.commit()
