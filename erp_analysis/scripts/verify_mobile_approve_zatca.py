"""End-to-end timing check: approve_document sets zatca_deferred on Sales Invoice path."""

from __future__ import annotations

import time

import frappe


def run(invoice_name: str):
	frappe.set_user("sakeer@printechs.com")
	from erp_analysis.approvals import approve_document

	start = time.time()
	try:
		result = approve_document(
			doctype="Sales Invoice",
			docname=invoice_name,
			action="Approve",
		)
		elapsed = round(time.time() - start, 2)
		msg = (result or {}).get("message") or {}
		print("elapsed_seconds", elapsed)
		print("status", msg.get("status"))
		print("docstatus", msg.get("docstatus"))
		print("zatca_deferred", msg.get("zatca_deferred"))
		print("zatca_status", msg.get("zatca_status"))
		frappe.db.commit()
	except Exception as exc:
		elapsed = round(time.time() - start, 2)
		print("elapsed_seconds", elapsed)
		print("FAILED", type(exc).__name__, str(exc)[:300])
		frappe.db.rollback()
