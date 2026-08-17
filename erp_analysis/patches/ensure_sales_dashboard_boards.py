"""Add Sales module dashboard boards (Option 1B) without changing home dashboard."""

from __future__ import annotations

import frappe

from erp_analysis.fixtures.printechs_b2b_profile import PROFILE_NAME
from erp_analysis.fixtures.sales_dashboard_widgets import (
	SALES_DASHBOARD_BOARDS,
	SALES_DASHBOARD_DEPRECATED_MODULE_KEYS,
	SALES_DASHBOARD_TEST_MODULE,
	SALES_DASHBOARD_WIDGETS,
)

SALES_DASHBOARD_DEPRECATED_WIDGET_KEYS = frozenset({"sales_dash_by_salesperson"})


def _upsert_board(doc, row: dict) -> None:
	key = row["dashboard_key"]
	existing = next((d for d in doc.dashboards or [] if d.dashboard_key == key), None)
	if existing:
		for field, value in row.items():
			if field == "dashboard_key":
				continue
			existing.set(field, value)
		return
	doc.append("dashboards", row)


def _upsert_widget(doc, row: dict) -> None:
	key = row["widget_key"]
	existing = next((w for w in doc.dashboard_widgets or [] if w.widget_key == key), None)
	if existing:
		for field, value in row.items():
			if field == "widget_key":
				continue
			existing.set(field, value)
		return
	doc.append("dashboard_widgets", row)


def _upsert_module(doc, row: dict) -> None:
	key = row["module_key"]
	existing = next((m for m in doc.modules or [] if m.module_key == key), None)
	if existing:
		for field, value in row.items():
			if field == "module_key":
				continue
			existing.set(field, value)
		return
	doc.append("modules", row)


def execute() -> dict:
	if not frappe.db.exists("DocType", "Mobile App Profile"):
		return {"ok": False, "reason": "Mobile App Profile DocType missing — run bench migrate first"}

	if not frappe.db.exists("Mobile App Profile", PROFILE_NAME):
		from erp_analysis.fixtures.printechs_b2b_profile import ensure_profile

		ensure_profile(update_existing=False)
		if not frappe.db.exists("Mobile App Profile", PROFILE_NAME):
			return {"ok": False, "reason": f"Profile {PROFILE_NAME} could not be created"}

	doc = frappe.get_doc("Mobile App Profile", PROFILE_NAME)
	home_widget_count_before = len(
		[w for w in doc.dashboard_widgets or [] if (w.dashboard_id or "home") == "home" and w.enabled]
	)

	for row in SALES_DASHBOARD_BOARDS:
		_upsert_board(doc, row)

	_upsert_module(doc, SALES_DASHBOARD_TEST_MODULE)

	disabled_modules: list[str] = []
	for mod in doc.modules or []:
		if mod.module_key in SALES_DASHBOARD_DEPRECATED_MODULE_KEYS and mod.enabled:
			mod.enabled = 0
			disabled_modules.append(mod.module_key)

	updated_keys: list[str] = []
	for row in SALES_DASHBOARD_WIDGETS:
		_upsert_widget(doc, row)
		updated_keys.append(row["widget_key"])

	disabled_keys: list[str] = []
	for widget in doc.dashboard_widgets or []:
		if widget.widget_key in SALES_DASHBOARD_DEPRECATED_WIDGET_KEYS and widget.enabled:
			widget.enabled = 0
			disabled_keys.append(widget.widget_key)

	doc.save(ignore_permissions=True)
	frappe.db.commit()

	home_widget_count_after = len(
		[w for w in doc.dashboard_widgets or [] if (w.dashboard_id or "home") == "home" and w.enabled]
	)

	return {
		"ok": True,
		"profile": PROFILE_NAME,
		"default_dashboard": doc.default_dashboard,
		"boards_added": [b["dashboard_key"] for b in SALES_DASHBOARD_BOARDS],
		"test_module": SALES_DASHBOARD_TEST_MODULE["module_key"],
		"disabled_modules": disabled_modules,
		"updated_widgets": updated_keys,
		"disabled_widgets": disabled_keys,
		"home_widget_count_unchanged": home_widget_count_before == home_widget_count_after,
		"home_widget_count": home_widget_count_after,
		"sales_overview_widget_count": len(
			[
				w
				for w in doc.dashboard_widgets or []
				if (w.dashboard_id or "") == "sales_overview" and w.enabled
			]
		),
	}
