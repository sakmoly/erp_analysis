#!/usr/bin/env python3
"""Export users, roles, permissions, and Access Profiles for safety backup.

Usage:
  bench --site site1.local execute erp_analysis.scripts.export_user_permissions.run
  bench --site site1.local execute erp_analysis.scripts.export_user_permissions.run --kwargs '{"output_dir": "/path/to/backups"}'
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

import frappe


def _rows(query: str, params: dict | None = None) -> list[dict[str, Any]]:
	return frappe.db.sql(query, params or {}, as_dict=True)


def _export_users() -> list[dict[str, Any]]:
	users = frappe.get_all(
		"User",
		filters={
			"enabled": 1,
			"user_type": "System User",
			"name": ["not in", ["Guest", "Administrator"]],
		},
		fields=[
			"name",
			"full_name",
			"email",
			"enabled",
			"user_type",
			"role_profile_name",
			"module_profile",
			"desk_theme",
			"language",
			"time_zone",
		],
		order_by="name asc",
		limit_page_length=0,
	)
	for user in users:
		user["roles"] = frappe.get_all(
			"Has Role",
			filters={"parent": user["name"], "parenttype": "User"},
			pluck="role",
			order_by="role asc",
		)
		user["user_permissions"] = frappe.get_all(
			"User Permission",
			filters={"user": user["name"]},
			fields=[
				"allow",
				"for_value",
				"apply_to_all_doctypes",
				"applicable_for",
				"is_default",
				"hide_descendants",
			],
			order_by="allow asc, for_value asc",
		)
		user["block_modules"] = frappe.get_all(
			"Block Module",
			filters={"parent": user["name"], "parenttype": "User"},
			pluck="module",
			order_by="module asc",
		)
	return users


def _export_access_profiles() -> list[dict[str, Any]]:
	if not frappe.db.exists("DocType", "Access Profile"):
		return []

	profiles = frappe.get_all(
		"Access Profile",
		fields=["name", "user", "company", "branch", "enabled", "modified"],
		order_by="name asc",
		limit_page_length=0,
	)
	meta = frappe.get_meta("Access Profile")
	out = []
	for row in profiles:
		doc = frappe.get_doc("Access Profile", row.name)
		item = doc.as_dict()
		if not meta.has_field("mobile_app_profile"):
			item.pop("mobile_app_profile", None)
		# Trim child row noise
		for child in ("access_rules", "territories", "approve_territories"):
			if child in item and isinstance(item[child], list):
				for line in item[child]:
					for k in ("creation", "modified", "owner", "modified_by", "parent", "parenttype", "parentfield"):
						line.pop(k, None)
		out.append(item)
	return out


def _export_custom_docperm() -> list[dict[str, Any]]:
	return _rows(
		"""
		SELECT parent AS doctype, role, permlevel,
			`read`, `write`, `create`, `delete`, submit, cancel, amend,
			report, export, import, share, print, email
		FROM `tabCustom DocPerm`
		ORDER BY parent, role, permlevel
		"""
	)


def _export_roles() -> list[dict[str, Any]]:
	return frappe.get_all(
		"Role",
		filters={"disabled": 0},
		fields=["name", "desk_access", "is_custom", "restrict_to_domain"],
		order_by="name asc",
		limit_page_length=0,
	)


def _export_mobile_app_settings() -> dict[str, Any]:
	if not frappe.db.exists("DocType", "Mobile App Settings"):
		return {}
	try:
		doc = frappe.get_single("Mobile App Settings")
		return doc.as_dict()
	except Exception:
		return {}


def run(output_dir: str | None = None):
	"""Write JSON safety backup; returns paths written."""
	site = frappe.local.site
	ts = datetime.now().strftime("%Y%m%d_%H%M%S")
	base = output_dir or os.path.join(
		frappe.get_app_path("erp_analysis"),
		"backups",
		"permissions",
		f"{site}_{ts}",
	)
	os.makedirs(base, exist_ok=True)

	payload = {
		"exported_at": datetime.now().isoformat(),
		"site": site,
		"erp_analysis_version": frappe.get_attr("erp_analysis.__version__"),
		"users": _export_users(),
		"roles": _export_roles(),
		"access_profiles": _export_access_profiles(),
		"custom_docperm": _export_custom_docperm(),
		"mobile_app_settings": _export_mobile_app_settings(),
		"counts": {},
	}

	payload["counts"] = {
		"users": len(payload["users"]),
		"roles": len(payload["roles"]),
		"access_profiles": len(payload["access_profiles"]),
		"custom_docperm": len(payload["custom_docperm"]),
		"total_user_roles": sum(len(u.get("roles") or []) for u in payload["users"]),
		"total_user_permissions": sum(len(u.get("user_permissions") or []) for u in payload["users"]),
	}

	files = {}
	for key in ("users", "roles", "access_profiles", "custom_docperm", "mobile_app_settings"):
		path = os.path.join(base, f"{key}.json")
		with open(path, "w", encoding="utf-8") as fh:
			json.dump(payload[key], fh, indent=2, default=str, sort_keys=True)
		files[key] = path

	summary_path = os.path.join(base, "summary.json")
	with open(summary_path, "w", encoding="utf-8") as fh:
		json.dump(
			{
				"exported_at": payload["exported_at"],
				"site": payload["site"],
				"erp_analysis_version": payload["erp_analysis_version"],
				"counts": payload["counts"],
				"files": files,
			},
			fh,
			indent=2,
			default=str,
		)

	frappe.response["message"] = {
		"ok": True,
		"directory": base,
		"summary": summary_path,
		"counts": payload["counts"],
	}
	return frappe.response["message"]
