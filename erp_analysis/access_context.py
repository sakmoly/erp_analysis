"""Central access + mobile profile context (Phase B/G)."""

from __future__ import annotations

from typing import Any, Literal, Optional

import frappe
from frappe import _

from erp_analysis.security import require_authenticated_user
from erp_analysis.services.mobile_profile import get_profile_context, resolve_mobile_app_profile_name

# Map logical module keys to API object_key substrings (Access Object Registry).
MODULE_API_HINTS: dict[str, tuple[str, ...]] = {
	"sales": (
		"erp_analysis.sales_kpis.",
		"erp_analysis.sales_performance.",
		"erp_analysis.sales.",
		"erp_analysis.dashboard.get_complete_dashboard_data",
		"erp_analysis.dashboard.get_sales",
		"erp_analysis.sales_kpis.get_sales_dashboard",
		"erp_analysis.analytics.",
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


def get_authenticated_access_context(
	user: Optional[str] = None,
	company: Optional[str] = None,
) -> dict[str, Any]:
	"""Authenticated user + Access Profile scope + optional Mobile App Profile."""
	user = require_authenticated_user() if not user or user == "Guest" else user

	from erp_analysis.api import _get_my_access

	access = _get_my_access(user=user, company=company)
	profile_name = resolve_mobile_app_profile_name(user=user, company=company)
	effective_company = get_effective_company(user=user, requested=company, access=access)

	return {
		"user": user,
		"company": effective_company,
		"access": access,
		"mobile_app_profile": profile_name,
		"profile_context": get_profile_context(user=user, company=effective_company) if profile_name else None,
		"view_territories": get_effective_view_territories(user=user, company=effective_company),
		"approve_territories": get_effective_approve_territories(user=user, company=effective_company),
	}


def get_mobile_profile_for_user(
	user: Optional[str] = None,
	company: Optional[str] = None,
) -> Optional[str]:
	return resolve_mobile_app_profile_name(user=user, company=company)


def is_module_enabled_in_profile(
	module_key: str,
	user: Optional[str] = None,
	company: Optional[str] = None,
) -> bool:
	"""True when no profile is linked (fallback) or profile enables the module."""
	from erp_analysis.services.mobile_profile import get_profile_modules

	profile_name = resolve_mobile_app_profile_name(user=user, company=company)
	if not profile_name:
		return True

	key = (module_key or "").strip().lower()
	for row in get_profile_modules(profile_name):
		if (row.get("key") or "").lower() == key:
			return bool(row.get("enabled"))
	return False


def get_effective_company(
	user: Optional[str] = None,
	requested: Optional[str] = None,
	access: Optional[dict[str, Any]] = None,
) -> Optional[str]:
	"""Resolve company — Access Profile company wins; reject cross-company requests."""
	user = user or frappe.session.user
	if access is None:
		from erp_analysis.api import _get_my_access

		access = _get_my_access(user=user, company=requested)

	scope = access.get("scope") or {}
	profile_company = scope.get("company")
	if profile_company:
		if requested and requested != profile_company:
			frappe.throw(
				_("Company {0} is outside your access scope").format(requested),
				frappe.PermissionError,
			)
		return profile_company
	if requested:
		return requested
	return frappe.defaults.get_user_default("Company")


def get_effective_view_territories(
	user: Optional[str] = None,
	company: Optional[str] = None,
	*,
	expand: bool = True,
) -> Optional[list[str]]:
	from erp_analysis.permissions.access_profile import get_view_territories

	return get_view_territories(user=user, company=company, expand=expand)


def get_effective_approve_territories(
	user: Optional[str] = None,
	company: Optional[str] = None,
	*,
	expand: bool = True,
) -> Optional[list[str]]:
	from erp_analysis.permissions.access_profile import get_approve_territories

	return get_approve_territories(user=user, company=company, expand=expand)


def resolve_view_territory_scope(
	requested: Optional[str] = None,
	requested_list: Optional[str | list[str]] = None,
	user: Optional[str] = None,
	company: Optional[str] = None,
	*,
	module: Optional[str] = None,
) -> Optional[list[str]]:
	from erp_analysis.permissions.access_profile import resolve_territory_scope

	return resolve_territory_scope(
		requested=requested,
		requested_list=requested_list,
		user=user,
		company=company,
		purpose="view",
		module=module,
	)


def resolve_approve_territory_scope(
	requested: Optional[str] = None,
	requested_list: Optional[str | list[str]] = None,
	user: Optional[str] = None,
	company: Optional[str] = None,
) -> Optional[list[str]]:
	from erp_analysis.permissions.access_profile import resolve_territory_scope

	return resolve_territory_scope(
		requested=requested,
		requested_list=requested_list,
		user=user,
		company=company,
		purpose="approve",
	)


def resolve_stock_warehouse_scope(
	requested: Optional[str] = None,
	user: Optional[str] = None,
	company: Optional[str] = None,
) -> Optional[list[str]]:
	from erp_analysis.permissions.access_profile import resolve_warehouse_scope

	return resolve_warehouse_scope(requested=requested, user=user, company=company)


def require_module_access(
	module_key: str,
	user: Optional[str] = None,
	company: Optional[str] = None,
) -> None:
	"""Reject when Mobile App Profile disables the module or Access Profile omits it."""
	user = user or frappe.session.user
	key = (module_key or "").strip().lower()
	if not key:
		return

	if not is_module_enabled_in_profile(key, user=user, company=company):
		frappe.throw(
			_("Module {0} is not enabled for your mobile profile").format(key),
			frappe.PermissionError,
		)

	allowed = _allowed_module_keys_for_access(user, company)
	if allowed is not None and key not in allowed:
		frappe.throw(
			_("Module {0} is not permitted by your Access Profile").format(key),
			frappe.PermissionError,
		)


def require_object_access(
	object_key: str,
	permission: Literal["can_view", "can_approve", "can_export", "can_create", "can_edit"] = "can_view",
	user: Optional[str] = None,
	company: Optional[str] = None,
	territory: Optional[str] = None,
	branch: Optional[str] = None,
) -> None:
	"""Enforce Access Profile object line when the user has a profile."""
	from erp_analysis.permissions.access_profile import PermissionDenied, _get_user_profile_name, evaluate

	user = user or frappe.session.user
	if not _get_user_profile_name(user, company):
		return

	try:
		decision = evaluate(user, company or get_effective_company(user), territory, branch, object_key)
	except PermissionDenied as exc:
		frappe.throw(str(exc), frappe.PermissionError)

	if not decision.get(permission):
		frappe.throw(
			_("Access denied for {0}").format(object_key),
			frappe.PermissionError,
		)


def assert_customer_in_view_scope(
	customer: str,
	user: Optional[str] = None,
	company: Optional[str] = None,
) -> None:
	"""Block Customer 360 when the customer territory is outside view scope."""
	from erp_analysis.permissions.access_profile import assert_document_territory_allowed

	if not customer or not frappe.db.exists("Customer", customer):
		return

	territory = frappe.db.get_value("Customer", customer, "territory")
	assert_document_territory_allowed(doc_territory=territory, user=user, company=company, purpose="view")


def guard_mobile_api(
	company: Optional[str] = None,
	module_key: Optional[str] = None,
	object_key: Optional[str] = None,
	territory: Optional[str] = None,
	*,
	scope_module: Optional[str] = None,
) -> dict[str, Any]:
	"""
	Standard mobile API entry guard.

	Returns authenticated context with resolved company and territory scope.
	"""
	ctx = get_authenticated_access_context(user=None, company=company)
	user = ctx["user"]
	company = ctx["company"]

	if module_key:
		require_module_access(module_key, user=user, company=company)
	if object_key:
		require_object_access(object_key, user=user, company=company, territory=territory)

	view_territories = resolve_view_territory_scope(
		requested=territory,
		user=user,
		company=company,
		module=scope_module,
	)
	ctx["company"] = company
	ctx["view_territory_scope"] = view_territories
	return ctx


def _allowed_module_keys_for_access(user: str, company: Optional[str]) -> Optional[set[str]]:
	"""None => no Access Profile module filter (legacy wide access)."""
	from erp_analysis.permissions.access_profile import _get_user_profile_name, get_lines, get_registry_map

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

	for shell in ("push", "settings"):
		allowed_modules.add(shell)
	return allowed_modules
