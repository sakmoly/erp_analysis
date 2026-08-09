"""Customer DocType permissions for mobile Customer 360 users."""

from __future__ import annotations

import json
from typing import Any, Optional

import frappe

CUSTOMER_360_OBJECT_KEYS = frozenset(
	{
		"erp_analysis.customer_360.get_customer_360",
		"erp_analysis.customer.get_customer_360",
		"erp_analysis.customer.search_customers",
	}
)


def _company_for_user(user: str | None = None) -> Optional[str]:
	user = user or frappe.session.user
	return frappe.defaults.get_user_default("Company", user) or frappe.db.get_default("Company", user)


def _user_has_customer_360_access(user: str | None = None) -> bool:
	user = user or frappe.session.user
	if not user or user == "Guest":
		return False
	if user == "Administrator":
		return True

	from erp_analysis.permissions.access_profile import PermissionDenied, evaluate

	company = _company_for_user(user)
	if not company:
		return False

	for object_key in CUSTOMER_360_OBJECT_KEYS:
		try:
			decision = evaluate(user, company, None, None, object_key)
		except PermissionDenied:
			continue
		except Exception:
			frappe.log_error(title="customer_360 permission check", message=frappe.get_traceback())
			continue
		if decision.get("can_view"):
			return True
	return False


def _allowed_territories(user: str | None = None, company: str | None = None) -> Optional[set[str]]:
	"""Territories from Access Profile, or None when profile does not restrict territory."""
	user = user or frappe.session.user
	company = company or _company_for_user(user)
	if not company:
		return set()

	from erp_analysis.permissions.access_profile import get_profile, _get_territory_map

	profile = get_profile(user, company, None, None)
	if not profile:
		return set()
	territories = _get_territory_map().get(profile.name)
	if not territories:
		return None
	return set(territories)


def _parse_json_arg(value: Any) -> Any:
	if isinstance(value, str):
		value = value.strip()
		if value.startswith("[") or value.startswith("{"):
			try:
				return json.loads(value)
			except Exception:
				return value
	return value


def _merge_territory_filter(filters: Any, territories: set[str]) -> dict | list:
	filters = _parse_json_arg(filters) or {}
	territory_filter = ["in", sorted(territories)]

	if isinstance(filters, dict):
		merged = dict(filters)
		if merged.get("territory"):
			requested = merged["territory"]
			if isinstance(requested, (list, tuple)) and requested and requested[0].lower() == "in":
				allowed = set(requested[1:]) & territories
				merged["territory"] = ["in", sorted(allowed)] if allowed else ["in", []]
			elif requested in territories:
				merged["territory"] = requested
			else:
				merged["territory"] = ["in", []]
		else:
			merged["territory"] = territory_filter
		return merged

	if isinstance(filters, list):
		merged = list(filters)
		merged.append(["territory", "in", sorted(territories)])
		return merged

	return {"territory": territory_filter}


def _strip_client_only_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
	clean = dict(kwargs)
	for key in ("parent", "expand", "as_dict", "debug"):
		clean.pop(key, None)
	return clean


def _customer_get_list_kwargs(
	user: str,
	company: str | None,
	filters: Any = None,
	or_filters: Any = None,
	**kwargs: Any,
) -> dict[str, Any]:
	allowed_territories = _allowed_territories(user, company)
	list_kwargs = dict(kwargs)
	list_kwargs["filters"] = filters
	list_kwargs["or_filters"] = or_filters
	list_kwargs["ignore_permissions"] = True

	if allowed_territories is not None:
		list_kwargs["filters"] = _merge_territory_filter(filters, allowed_territories)

	return _strip_client_only_kwargs(list_kwargs)


def patch_user_permission_for_customer_360():
	"""Allow Customer 360 users to read Customer despite territory User Permissions."""
	import frappe.permissions as permissions_module

	if getattr(permissions_module, "_erp_analysis_customer_360_patched", False):
		return

	original = permissions_module.has_user_permission

	def has_user_permission(doc, user=None, debug=False, ptype=None):
		if (
			doc
			and getattr(doc, "doctype", None) == "Customer"
			and ptype in (None, "read")
			and _user_has_customer_360_access(user)
		):
			return True
		return original(doc, user=user, debug=debug, ptype=ptype)

	permissions_module.has_user_permission = has_user_permission
	permissions_module._erp_analysis_customer_360_patched = True


def apply_customer_360_permission_patch():
	patch_user_permission_for_customer_360()
