"""Import ERP Analysis Desk workspace (existing sites that installed before workspace JSON existed)."""

from __future__ import annotations

import os

import frappe
from frappe.modules.import_file import import_file_by_path


def ensure_erp_analysis_desk_workspace() -> dict:
	app_path = frappe.get_app_path("erp_analysis")
	json_path = os.path.join(
		app_path,
		"erp_analysis",
		"workspace",
		"erp_analysis",
		"erp_analysis.json",
	)
	if not os.path.isfile(json_path):
		return {"ok": False, "reason": f"missing {json_path}"}

	import_file_by_path(json_path, force=True, ignore_version=True)
	frappe.db.commit()
	exists = frappe.db.exists("Workspace", "ERP Analysis")
	return {"ok": bool(exists), "workspace": "ERP Analysis"}


def execute():
	return ensure_erp_analysis_desk_workspace()
