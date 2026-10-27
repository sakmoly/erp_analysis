"""Enable payables (and purchase) modules on PRINTECHS-B2B Mobile App Profile."""

from __future__ import annotations

import frappe

from erp_analysis.mobile_module_icons import DEFAULT_MODULE_ICON_KEYS

PROFILE_NAME = "PRINTECHS-B2B"

_MODULE_ROWS = (
	{
		"module_key": "payables",
		"label": "Payables",
		"enabled": 1,
		"sort_order": 15,
		"route_key": "payables",
		"icon_key": DEFAULT_MODULE_ICON_KEYS.get("payables"),
		"screen_type": "module",
	},
	{
		"module_key": "purchase",
		"label": "Purchase",
		"enabled": 1,
		"sort_order": 16,
		"route_key": "purchase",
		"icon_key": DEFAULT_MODULE_ICON_KEYS.get("purchase"),
		"screen_type": "module",
	},
)


def execute():
	if not frappe.db.exists("Mobile App Profile", PROFILE_NAME):
		return

	doc = frappe.get_doc("Mobile App Profile", PROFILE_NAME)
	existing = {(row.module_key or "").strip().lower() for row in doc.modules or []}
	changed = False
	for row in _MODULE_ROWS:
		key = row["module_key"]
		if key in existing:
			for mod in doc.modules or []:
				if (mod.module_key or "").strip().lower() == key:
					if not mod.enabled:
						mod.enabled = 1
						changed = True
					if not (mod.route_key or "").strip():
						mod.route_key = row["route_key"]
						changed = True
			continue
		doc.append("modules", row)
		changed = True

	if changed:
		doc.save(ignore_permissions=True)
		frappe.db.commit()
