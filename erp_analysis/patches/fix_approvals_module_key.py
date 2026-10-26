"""Fix Mobile App Profile module_key Approval → approvals (bootstrap + access alignment)."""

from __future__ import annotations

import frappe


def execute():
	if not frappe.db.exists("DocType", "Mobile App Profile"):
		return

	changed = 0
	for profile_name in frappe.get_all("Mobile App Profile", pluck="name"):
		doc = frappe.get_doc("Mobile App Profile", profile_name)
		profile_changed = False
		for row in doc.modules or []:
			raw = (row.module_key or "").strip()
			if raw.lower() in ("approval", "approvals") and raw != "approvals":
				row.module_key = "approvals"
				profile_changed = True
			if (row.route_key or "").strip().lower() in ("approval", "") and row.module_key == "approvals":
				row.route_key = "approvals"
				profile_changed = True
			if not (row.label or "").strip():
				row.label = "Approvals"
		if profile_changed:
			doc.save(ignore_permissions=True)
			changed += 1

	frappe.db.commit()
	if changed:
		frappe.logger("erp_analysis").info(f"fix_approvals_module_key: updated {changed} Mobile App Profile(s)")
