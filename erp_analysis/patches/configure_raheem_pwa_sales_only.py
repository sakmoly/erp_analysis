"""PWA pilot: raheem@printechs.com — login allowed; Access Profile view limited to Sales."""

from __future__ import annotations

import frappe

USER = "raheem@printechs.com"
PROFILE_NAME = "AP-raheem@printechs.com-00001"

# Menus kept visible in mobile / PWA navigation.
SALES_MENU_KEYS = frozenset({"menu_dashboard", "menu_sales_performance"})

# Menus and API prefixes denied (view-only sales).
DENY_MENU_KEYS = frozenset(
	{
		"menu_receivables",
		"menu_inventory",
		"menu_payables",
		"menu_purchase_performance",
		"menu_approvals",
		"menu_employees",
		"menu_settings",
	}
)
DENY_API_PREFIXES = (
	"erp_analysis.receivables.",
	"erp_analysis.inventory.",
	"erp_analysis.stock.",
	"printechs_utility.inventory.",
	"erp_analysis.collection.",
	"erp_analysis.approvals.",
	"erp_analysis.executive.",
	"erp_analysis.payables.",
	"erp_analysis.purchase.",
)


def execute() -> None:
	if not frappe.db.exists("Access Profile", PROFILE_NAME):
		frappe.logger("erp_analysis").warning("Access Profile %s not found — skip", PROFILE_NAME)
		return

	profile = frappe.get_doc("Access Profile", PROFILE_NAME)
	registry = {
		row.name: row.object_key
		for row in frappe.get_all("Access Object Registry", fields=["name", "object_key"])
	}

	for line in profile.access_rules:
		obj_key = registry.get(line.access_object) or ""
		if obj_key in DENY_MENU_KEYS or any(obj_key.startswith(p) for p in DENY_API_PREFIXES):
			line.can_view = 0
		elif obj_key in SALES_MENU_KEYS:
			line.can_view = 1

	profile.enabled = 1
	profile.save(ignore_permissions=True)
	frappe.db.commit()
	frappe.logger("erp_analysis").info("Configured %s for PWA sales-only view", USER)
