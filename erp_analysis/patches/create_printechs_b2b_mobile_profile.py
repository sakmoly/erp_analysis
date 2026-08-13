"""Phase J — create PRINTECHS-B2B Mobile App Profile if missing (no user/profile links)."""

import frappe

from erp_analysis.fixtures.printechs_b2b_profile import ensure_profile


def execute():
	"""Idempotent: creates profile document only; never links Access Profiles or Settings."""
	if frappe.flags.in_install or frappe.flags.in_migrate:
		result = ensure_profile()
		if result.get("created"):
			frappe.logger("erp_analysis").info("Created Mobile App Profile PRINTECHS-B2B")
		return result
	return ensure_profile()
