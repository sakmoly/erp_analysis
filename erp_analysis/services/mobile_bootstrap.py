"""Mobile bootstrap payload (Phase C)."""

from __future__ import annotations

from typing import Any, Optional

import frappe
from frappe.utils import get_url

from erp_analysis import __version__ as APP_VERSION
from erp_analysis.mobile_config import get_mobile_config_cached
from erp_analysis.mobile_module_icons import get_module_icon_key
from erp_analysis.access_context import _allowed_module_keys_for_access, get_effective_company
from erp_analysis.security import require_authenticated_user
from erp_analysis.services.mobile_profile import (
	get_profile_branding,
	get_profile_modules,
	get_profile_widgets,
	resolve_mobile_app_profile_name,
)

BOOTSTRAP_SCHEMA_VERSION = 1

DIMENSION_LABELS: dict[str, str] = {
	"company": "Company",
	"territory": "Territory",
	"warehouse": "Warehouse",
	"brand": "Brand",
	"division": "Division",
	"department": "Department",
	"cost_center": "Cost Center",
	"branch": "Branch",
}


def build_mobile_bootstrap(
	user: Optional[str] = None,
	company: Optional[str] = None,
) -> dict[str, Any]:
	"""Assemble authenticated mobile bootstrap (server-resolved profile + access)."""
	user = require_authenticated_user() if not user or user == "Guest" else user

	from erp_analysis.api import _get_my_access

	access = _get_my_access(user=user, company=company)
	company = get_effective_company(user=user, requested=company, access=access)
	profile_name = resolve_mobile_app_profile_name(user=user, company=company)
	legacy_config = get_mobile_config_cached()

	modules = _build_modules(user, company, profile_name, legacy_config, access)
	dimensions = _build_dimensions(profile_name, legacy_config)
	dashboard = _build_dashboard(profile_name, legacy_config)
	branding = _build_branding(profile_name, legacy_config)
	context = _build_context(user, company, profile_name, access)
	capabilities = _build_capabilities(access)

	return {
		"schema_version": BOOTSTRAP_SCHEMA_VERSION,
		"api_version": APP_VERSION,
		"user": _build_user_block(user),
		"context": context,
		"branding": branding,
		"modules": modules,
		"dimensions": dimensions,
		"dashboard": dashboard,
		"permissions": {
			"scope": access.get("scope") or {},
			"objects": access.get("profiles") or [],
		},
		"capabilities": capabilities,
		"meta": {
			"schema_version": BOOTSTRAP_SCHEMA_VERSION,
			"api_version": APP_VERSION,
			"config_source": "mobile_app_profile" if profile_name else "mobile_app_settings",
		},
	}


def _build_user_block(user: str) -> dict[str, Any]:
	user_doc = frappe.db.get_value(
		"User",
		user,
		["email", "full_name", "user_image"],
		as_dict=True,
	) or {}
	return {
		"email": user_doc.get("email") or user,
		"full_name": user_doc.get("full_name") or user,
		"image_url": get_url(user_doc.user_image) if user_doc.get("user_image") else None,
	}


def _build_context(
	user: str,
	company: Optional[str],
	profile_name: Optional[str],
	access: dict[str, Any],
) -> dict[str, Any]:
	ctx: dict[str, Any] = {
		"company": company,
		"profile": profile_name,
		"business_type": None,
	}
	if profile_name and frappe.db.exists("Mobile App Profile", profile_name):
		ctx["business_type"] = frappe.db.get_value("Mobile App Profile", profile_name, "business_type")
		ctx["profile_display_name"] = frappe.db.get_value(
			"Mobile App Profile", profile_name, "profile_name"
		)

	scope = access.get("scope") or {}
	if scope:
		ctx["branch"] = scope.get("branch")
		ctx["territory"] = scope.get("territory")
		ctx["view_territories"] = scope.get("view_territories") or scope.get("territories") or []
		ctx["approve_territories"] = scope.get("approve_territories") or []
	return ctx


def _build_capabilities(access: dict[str, Any]) -> dict[str, Any]:
	scope = access.get("scope") or {}
	return {
		"allow_view_all_sales": bool(scope.get("allow_view_all_sales")),
		"allow_view_all_stock": bool(scope.get("allow_view_all_stock")),
		"allow_all_receivable": bool(scope.get("allow_all_receivable")),
	}


def _build_branding(profile_name: Optional[str], legacy_config: dict[str, Any]) -> dict[str, Any]:
	if profile_name:
		branding = get_profile_branding(profile_name)
		if branding.get("logo"):
			branding["logo_url"] = get_url(branding.pop("logo"))
		return {k: v for k, v in branding.items() if v not in (None, "")}

	return {
		"app_title": legacy_config.get("app") or "erp_analysis",
	}


def _build_modules(
	user: str,
	company: Optional[str],
	profile_name: Optional[str],
	legacy_config: dict[str, Any],
	access: dict[str, Any],
) -> list[dict[str, Any]]:
	config_modules: dict[str, bool] = legacy_config.get("modules") or {}
	allowed_by_access = _allowed_module_keys_for_access(user, company)

	if profile_name:
		candidates = get_profile_modules(profile_name)
	else:
		candidates = [
			{
				"key": key,
				"label": key.replace("_", " ").title(),
				"enabled": bool(config_modules.get(key, True)),
				"route_key": key,
				"icon_key": get_module_icon_key(key),
				"feature_key": None,
				"sort_order": idx,
			}
			for idx, key in enumerate(config_modules.keys())
			if config_modules.get(key, True)
		]

	out: list[dict[str, Any]] = []
	for row in candidates:
		key = (row.get("key") or "").strip()
		if not key:
			continue
		if not config_modules.get(key, True):
			continue
		if allowed_by_access is not None and key not in allowed_by_access:
			continue
		out.append(
			{
				"key": key,
				"label": row.get("label") or key,
				"enabled": bool(row.get("enabled", True)),
				"route_key": row.get("route_key") or key,
				"icon_key": get_module_icon_key(key, row.get("icon_key")),
				"feature_key": row.get("feature_key"),
			}
		)
	return out


def _build_dimensions(profile_name: Optional[str], legacy_config: dict[str, Any]) -> list[dict[str, Any]]:
	if profile_name:
		from erp_analysis.services.mobile_profile import get_profile_dimensions_public

		return get_profile_dimensions_public(profile_name)

	config_dims: dict[str, bool] = legacy_config.get("dimensions") or {}
	out = []
	for key, enabled in config_dims.items():
		if not enabled:
			continue
		out.append(
			{
				"key": key,
				"label": DIMENSION_LABELS.get(key, key.replace("_", " ").title()),
				"data_type": "Link" if key in ("company", "territory", "warehouse", "branch") else "Data",
				"filterable": True,
				"groupable": True,
				"sortable": False,
			}
		)
	return out


def _build_dashboard(profile_name: Optional[str], legacy_config: dict[str, Any]) -> list[dict[str, Any]]:
	if profile_name:
		return get_profile_widgets(profile_name)

	dashboards = legacy_config.get("dashboards") or []
	out: list[dict[str, Any]] = []
	for board in dashboards:
		if not isinstance(board, dict):
			continue
		for widget in board.get("widgets") or []:
			if not isinstance(widget, dict):
				continue
			out.append(
				{
					"key": widget.get("id") or widget.get("key"),
					"label": widget.get("title") or widget.get("label"),
					"widget_type": widget.get("type") or "LIST",
					"module_key": widget.get("module") or board.get("module"),
					"enabled": True,
				}
			)
	return out

