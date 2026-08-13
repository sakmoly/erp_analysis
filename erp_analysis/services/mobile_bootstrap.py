"""Mobile bootstrap payload (Phase C)."""

from __future__ import annotations

from typing import Any, Optional

import frappe
from frappe.utils import get_url

from erp_analysis import __version__ as APP_VERSION
from erp_analysis.mobile_config import get_mobile_config_cached
from erp_analysis.permissions.access_profile import get_lines, get_registry_map
from erp_analysis.permissions.access_profile import _get_user_profile_name
from erp_analysis.security import require_authenticated_user
from erp_analysis.services.mobile_profile import (
	get_profile_branding,
	get_profile_modules,
	get_profile_widgets,
	resolve_mobile_app_profile_name,
)

BOOTSTRAP_SCHEMA_VERSION = 1

# Map logical module keys to API object_key substrings (Access Object Registry).
MODULE_API_HINTS: dict[str, tuple[str, ...]] = {
	"sales": (
		"erp_analysis.sales_kpis.",
		"erp_analysis.sales_performance.",
		"erp_analysis.sales.",
		"erp_analysis.dashboard.get_complete_dashboard_data",
		"erp_analysis.dashboard.get_sales",
		"erp_analysis.sales_kpis.get_sales_dashboard",
	),
	"executive": ("erp_analysis.executive.", "erp_analysis.dashboard.get_executive_dashboard"),
	"collection": ("erp_analysis.collection.",),
	"sales_performance": ("erp_analysis.sales_performance.", "erp_analysis.sales.get_salesperson"),
	"sales_orders": ("erp_analysis.sales_orders.",),
	"receivables": ("erp_analysis.receivables.",),
	"inventory": ("erp_analysis.inventory.", "erp_analysis.stock.", "printechs_utility.inventory."),
	"payables": ("erp_analysis.payables.",),
	"purchase": ("erp_analysis.purchase.",),
	"customer_360": ("erp_analysis.customer_360.", "erp_analysis.customer."),
	"profitability": ("erp_analysis.profitability.",),
	"exceptions": ("erp_analysis.exceptions.",),
	"approval_analytics": (
		"erp_analysis.approval_analytics.",
		"erp_analysis.approvals.get_approval_analytics",
	),
	"approvals": ("erp_analysis.approvals.",),
	"catalogue": ("erp_analysis.catalogue.",),
	"push": ("erp_analysis.api.store_push_token",),
	"settings": ("erp_analysis.profile.", "erp_analysis.api.get_my_access"),
}

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
	company = _resolve_effective_company(user, company, access)
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


def _resolve_effective_company(
	user: str,
	requested: Optional[str],
	access: dict[str, Any],
) -> Optional[str]:
	scope = access.get("scope") or {}
	profile_company = scope.get("company")
	if profile_company:
		if requested and requested != profile_company:
			frappe.throw(
				frappe._("Company {0} is outside your access scope").format(requested),
				frappe.PermissionError,
			)
		return profile_company
	if requested:
		return requested
	return frappe.defaults.get_user_default("Company")


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
				"icon_key": None,
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
				"icon_key": row.get("icon_key"),
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


def _allowed_module_keys_for_access(user: str, company: Optional[str]) -> Optional[set[str]]:
	"""None => no Access Profile module filter (legacy wide access)."""
	profile_name = _get_user_profile_name(user, company)
	if not profile_name:
		return None

	registry = get_registry_map()
	lines = get_lines(profile_name)
	allowed_api_keys: set[str] = set()
	for line in lines:
		if not line.get("can_view"):
			continue
		access_object = line.get("access_object")
		reg = registry.get(access_object)
		if reg and reg.get("object_key"):
			allowed_api_keys.add(reg["object_key"])

	if not allowed_api_keys:
		return set()

	allowed_modules: set[str] = set()
	for module_key, hints in MODULE_API_HINTS.items():
		for api_key in allowed_api_keys:
			if any(api_key.startswith(h) or api_key == h for h in hints):
				allowed_modules.add(module_key)
				break

	# Shell modules (no analytics API gate).
	for shell in ("push", "settings"):
		allowed_modules.add(shell)
	return allowed_modules
