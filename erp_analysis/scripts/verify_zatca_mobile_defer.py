"""Verify mobile approve defers ZATCA to background queue."""

from __future__ import annotations

import frappe


def run(invoice_name: str | None = None, dry_run: bool = True):
	"""Check patch + optionally simulate defer enqueue (dry_run=True by default)."""
	frappe.set_user("Administrator")

	from erp_analysis.integrations import zatca_mobile_defer as defer_mod

	defer_mod.apply_zatca_mobile_defer_patch()

	import zatca_erpgulf.zatca_erpgulf.sign_invoice as sign_invoice

	wrapped = sign_invoice.zatca_background_on_submit
	patched = getattr(wrapped, "_erp_analysis_mobile_defer_patched", False)
	print("patch_active", patched)

	enqueued: list[dict] = []
	orig_enqueue = frappe.enqueue

	def capture_enqueue(method, **kwargs):
		enqueued.append({"method": method, "kwargs": {k: v for k, v in kwargs.items() if k != "job_name"}})
		if dry_run:
			return frappe._dict(name="dry-run-job")
		return orig_enqueue(method, **kwargs)

	frappe.enqueue = capture_enqueue

	if not invoice_name:
		invoice_name = frappe.db.get_value(
			"Sales Invoice",
			{"docstatus": 1, "custom_zatca_status": ["in", ["Not Submitted", "REPORTED", "CLEARED"]]},
			"name",
			order_by="modified desc",
		)
	if not invoice_name:
		invoice_name = frappe.db.get_value(
			"Sales Invoice", {"docstatus": 1}, "name", order_by="modified desc"
		)

	if not invoice_name:
		print("no_invoice")
		frappe.enqueue = orig_enqueue
		return

	doc = frappe.get_doc("Sales Invoice", invoice_name)
	print("probe_invoice", invoice_name, "docstatus", doc.docstatus)

	frappe.flags.defer_zatca_for_mobile_approve = True
	try:
		sign_invoice.zatca_background_on_submit(doc)
	finally:
		frappe.flags.defer_zatca_for_mobile_approve = False
		frappe.enqueue = orig_enqueue

	print("enqueue_calls", len(enqueued))
	for row in enqueued:
		print("  method", row["method"])
		print("  invoice", row["kwargs"].get("invoice_name"))

	if not dry_run and enqueued:
		print("waiting_for_worker...")
		frappe.db.commit()

	return {"patched": patched, "enqueued": enqueued, "invoice": invoice_name}
