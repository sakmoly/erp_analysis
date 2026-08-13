"""Mobile App Profile resolution and presentation payloads (Phase B)."""

from __future__ import annotations

import json
from typing import Any, Optional

import frappe

from erp_analysis.permissions.access_profile import _get_user_profile_name
from erp_analysis.services.mobile_dimensions import dimension_public_metadata, get_profile_dimensions

PROFILE_DOCTYPE = "Mobile App Profile"


def _parse_config_json(raw: Any) -> dict[str, Any]:
	if not raw:
		return {}
	if isinstance(raw, dict):
		return raw
	if isinstance(raw, str):
		try:
			parsed = json.loads(raw)
			return parsed if isinstance(parsed, dict) else {}
		except Exception:
			return {}
	return {}


def resolve_mobile_app_profile_name(
	user: Optional[str] = None,
	company: Optional[str] = None,
) -> Optional[str]:
	"""
	Resolve Mobile App Profile for authenticated context (server-side only).

	Precedence:
	  1. Enabled Access Profile → mobile_app_profile (when field exists and is set)
	  2. Mobile App Settings → default_mobile_app_profile
	  3. None → caller uses Mobile App Settings / code defaults (unchanged behavior)
	"""
	user = user or frappe.session.user
	if not user or user == "Guest":
		return None

	access_profile_name = _get_user_profile_name(user, company)
	if access_profile_name:
		linked = _read_access_profile_mobile_link(access_profile_name)
		if linked and _profile_is_active(linked):
			return linked

	return _read_settings_default_profile()


def _read_access_profile_mobile_link(access_profile_name: str) -> Optional[str]:
	meta = frappe.get_meta("Access Profile")
	if not meta.has_field("mobile_app_profile"):
		return None
	return frappe.db.get_value("Access Profile", access_profile_name, "mobile_app_profile")


def _read_settings_default_profile() -> Optional[str]:
	if not frappe.db.exists("DocType", "Mobile App Settings"):
		return None
	meta = frappe.get_meta("Mobile App Settings")
	if not meta.has_field("default_mobile_app_profile"):
		return None
	profile = frappe.db.get_single_value("Mobile App Settings", "default_mobile_app_profile")
	if profile and _profile_is_active(profile):
		return profile
	return None


def _profile_is_active(profile_name: str) -> bool:
	if not profile_name or not frappe.db.exists(PROFILE_DOCTYPE, profile_name):
		return False
	return bool(frappe.db.get_value(PROFILE_DOCTYPE, profile_name, "enabled"))


def get_mobile_app_profile(profile_name: str) -> Optional[frappe.model.document.Document]:
	if not profile_name or not frappe.db.exists(PROFILE_DOCTYPE, profile_name):
		return None
	doc = frappe.get_doc(PROFILE_DOCTYPE, profile_name)
	if not doc.enabled:
		return None
	return doc


def get_profile_modules(profile_name: str, *, enabled_only: bool = True) -> list[dict[str, Any]]:
	doc = get_mobile_app_profile(profile_name)
	if not doc:
		return []

	rows = []
	for row in doc.modules or []:
		if enabled_only and not row.enabled:
			continue
		key = (row.module_key or "").strip()
		if not key:
			continue
		rows.append(
			{
				"key": key,
				"label": row.label or key,
				"enabled": bool(row.enabled),
				"route_key": row.route_key or key,
				"icon_key": row.icon_key,
				"feature_key": row.feature_key,
				"sort_order": row.sort_order or 0,
			}
		)
	rows.sort(key=lambda r: (r.get("sort_order") or 0, r.get("label") or ""))
	return rows


def get_profile_dimensions_public(profile_name: str) -> list[dict[str, Any]]:
	return [
		dimension_public_metadata(row)
		for row in get_profile_dimensions(profile_name, enabled_only=True)
	]


def _widget_row_public(row, *, default_board: str) -> dict[str, Any]:
	key = (row.widget_key or "").strip()
	board_id = (row.dashboard_id or default_board or "home").strip()
	return {
		"key": key,
		"label": row.label or key,
		"widget_type": row.widget_type,
		"dashboard_id": board_id,
		"metric_key": row.metric_key,
		"module_key": row.module_key,
		"dimension_key": row.dimension_key,
		"secondary_dimension_key": row.secondary_dimension_key,
		"size": row.size or "md",
		"sort_order": row.sort_order or 0,
		"config_json": row.config_json,
		"config": _parse_config_json(row.config_json),
	}


def get_profile_widgets(
	profile_name: str,
	*,
	enabled_only: bool = True,
	dashboard_id: Optional[str] = None,
) -> list[dict[str, Any]]:
	doc = get_mobile_app_profile(profile_name)
	if not doc:
		return []

	default_board = (doc.default_dashboard or "home").strip()
	rows = []
	for row in doc.dashboard_widgets or []:
		if enabled_only and not row.enabled:
			continue
		key = (row.widget_key or "").strip()
		if not key:
			continue
		public = _widget_row_public(row, default_board=default_board)
		if dashboard_id is not None:
			target = (dashboard_id or default_board).strip()
			if (public.get("dashboard_id") or default_board) != target:
				continue
		rows.append(public)
	rows.sort(key=lambda r: (r.get("sort_order") or 0, r.get("label") or ""))
	return rows


def get_profile_dashboard_boards(profile_name: str, *, enabled_only: bool = True) -> list[dict[str, Any]]:
	"""Return dashboard boards with nested widgets for bootstrap."""
	doc = get_mobile_app_profile(profile_name)
	if not doc:
		return []

	default_board = (doc.default_dashboard or "home").strip()
	all_widgets = get_profile_widgets(profile_name, enabled_only=enabled_only)
	board_rows = list(doc.dashboards or [])

	if not board_rows:
		return [
			{
				"key": default_board,
				"label": "Dashboard",
				"sort_order": 0,
				"icon_key": None,
				"widgets": all_widgets,
			}
		]

	boards: list[dict[str, Any]] = []
	for row in board_rows:
		if enabled_only and not row.enabled:
			continue
		board_key = (row.dashboard_key or "").strip()
		if not board_key:
			continue
		boards.append(
			{
				"key": board_key,
				"label": row.label or board_key,
				"sort_order": row.sort_order or 0,
				"icon_key": row.icon_key,
				"widgets": [
					w
					for w in all_widgets
					if (w.get("dashboard_id") or default_board) == board_key
				],
			}
		)
	boards.sort(key=lambda r: (r.get("sort_order") or 0, r.get("label") or ""))
	return boards


def get_profile_branding(profile_name: str) -> dict[str, Any]:
	doc = get_mobile_app_profile(profile_name)
	if not doc:
		return {}
	return {
		"app_title": doc.app_title,
		"app_subtitle": doc.app_subtitle,
		"logo": doc.logo,
		"primary_locale": doc.primary_locale,
		"currency_source": doc.currency_source,
		"default_dashboard": doc.default_dashboard,
	}


def get_profile_context(
	user: Optional[str] = None,
	company: Optional[str] = None,
) -> dict[str, Any]:
	"""Resolved profile metadata for bootstrap (Phase C) and internal callers."""
	profile_name = resolve_mobile_app_profile_name(user=user, company=company)
	if not profile_name:
		return {"profile": None}

	doc = get_mobile_app_profile(profile_name)
	if not doc:
		return {"profile": None}

	return {
		"profile": profile_name,
		"profile_name": doc.profile_name,
		"business_type": doc.business_type,
		"company": doc.company,
		"branding": get_profile_branding(profile_name),
		"modules": get_profile_modules(profile_name),
		"dimensions": get_profile_dimensions_public(profile_name),
		"dashboards": get_profile_dashboard_boards(profile_name),
		"dashboard_widgets": get_profile_widgets(profile_name),
	}
