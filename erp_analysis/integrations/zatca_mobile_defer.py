"""Defer synchronous ZATCA on_submit during mobile invoice approval."""

from __future__ import annotations

import frappe

_ORIGINAL_ZATCA_ON_SUBMIT = None


def apply_zatca_mobile_defer_patch() -> None:
	global _ORIGINAL_ZATCA_ON_SUBMIT
	try:
		import zatca_erpgulf.zatca_erpgulf.sign_invoice as sign_invoice
	except ImportError:
		return

	orig = sign_invoice.zatca_background_on_submit
	if getattr(orig, "_erp_analysis_mobile_defer_patched", False):
		return

	_ORIGINAL_ZATCA_ON_SUBMIT = orig

	def wrapped(doc, _method=None, bypass_background_check=False):
		if (
			not bypass_background_check
			and getattr(frappe.flags, "defer_zatca_for_mobile_approve", False)
			and getattr(doc, "doctype", None) == "Sales Invoice"
			and getattr(doc, "name", None)
		):
			frappe.enqueue(
				"erp_analysis.integrations.zatca_mobile_defer.submit_invoice_to_zatca",
				queue="long",
				timeout=600,
				invoice_name=doc.name,
				enqueue_after_commit=True,
			)
			return None
		return orig(doc, _method=_method, bypass_background_check=bypass_background_check)

	wrapped._erp_analysis_mobile_defer_patched = True
	sign_invoice.zatca_background_on_submit = wrapped


def submit_invoice_to_zatca(invoice_name: str) -> None:
	"""Background worker: run ZATCA after mobile approve returned."""
	if not invoice_name or not frappe.db.exists("Sales Invoice", invoice_name):
		return
	doc = frappe.get_doc("Sales Invoice", invoice_name)
	if doc.docstatus != 1:
		return
	if doc.meta.has_field("custom_zatca_status"):
		status = (doc.get("custom_zatca_status") or "").strip()
		if status in ("REPORTED", "CLEARED"):
			return
	orig = _ORIGINAL_ZATCA_ON_SUBMIT
	if not orig:
		from zatca_erpgulf.zatca_erpgulf.sign_invoice import zatca_background_on_submit as orig
	orig(doc, bypass_background_check=True)
	frappe.db.commit()
