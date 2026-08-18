"""Deploy Receivables Phase 1 dashboard board on PRINTECHS-B2B profile."""

from __future__ import annotations

from typing import Any

import frappe

from erp_analysis.fixtures.operations_dashboard_widgets import (
	DEPRECATED_WIDGET_KEYS,
	OPERATIONS_DASHBOARD_BOARDS,
	OPERATIONS_DASHBOARD_MODULES,
	PHASE1_DISABLED_WIDGET_KEYS,
	RECEIVABLES_PHASE1_WIDGETS,
)
from erp_analysis.fixtures.printechs_b2b_profile import PROFILE_NAME


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


def _update_home_receivables_link(doc) -> None:
	for widget in doc.dashboard_widgets or []:
		if widget.widget_key != "goto_receivables":
			continue
		widget.config_json = (
			'{"action": {"type": "navigate", "target": "dashboard", '
			'"dashboard_id": "receivables_overview"}}'
		)
		return


def execute() -> dict[str, Any]:
	if not frappe.db.exists("DocType", "Mobile App Profile"):
		return {"ok": False, "reason": "Mobile App Profile DocType missing — run bench migrate first"}

	if not frappe.db.exists("Mobile App Profile", PROFILE_NAME):
		from erp_analysis.fixtures.printechs_b2b_profile import ensure_profile

		ensure_profile(update_existing=False)
		if not frappe.db.exists("Mobile App Profile", PROFILE_NAME):
			return {"ok": False, "reason": f"Profile {PROFILE_NAME} could not be created"}

	doc = frappe.get_doc("Mobile App Profile", PROFILE_NAME)

	for row in OPERATIONS_DASHBOARD_BOARDS:
		_upsert_board(doc, row)

	for row in OPERATIONS_DASHBOARD_MODULES:
		_upsert_module(doc, row)

	updated_keys: list[str] = []
	for row in RECEIVABLES_PHASE1_WIDGETS:
		_upsert_widget(doc, row)
		updated_keys.append(row["widget_key"])

	disabled_keys: list[str] = []
	for widget in doc.dashboard_widgets or []:
		key = widget.widget_key or ""
		if key in DEPRECATED_WIDGET_KEYS and widget.enabled:
			widget.enabled = 0
			disabled_keys.append(key)
		if key in PHASE1_DISABLED_WIDGET_KEYS and widget.enabled:
			widget.enabled = 0
			disabled_keys.append(key)

	_update_home_receivables_link(doc)

	doc.save(ignore_permissions=True)
	frappe.db.commit()

	enabled_count = len(
		[
			w
			for w in doc.dashboard_widgets or []
			if (w.dashboard_id or "") == "receivables_overview" and w.enabled
		]
	)

	return {
		"ok": True,
		"profile": PROFILE_NAME,
		"board": "receivables_overview",
		"updated_widgets": updated_keys,
		"disabled_widgets": disabled_keys,
		"enabled_widget_count": enabled_count,
	}
