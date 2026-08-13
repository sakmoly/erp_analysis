"""Central access + mobile profile context (Phase B/G foundation)."""

from __future__ import annotations

from typing import Any, Optional

import frappe

from erp_analysis.security import require_authenticated_user
from erp_analysis.services.mobile_profile import get_profile_context, resolve_mobile_app_profile_name


def get_authenticated_access_context(
	user: Optional[str] = None,
	company: Optional[str] = None,
) -> dict[str, Any]:
	"""Authenticated user + Access Profile scope + optional Mobile App Profile."""
	user = require_authenticated_user() if not user or user == "Guest" else user

	from erp_analysis.api import _get_my_access

	access = _get_my_access(user=user, company=company)
	profile_name = resolve_mobile_app_profile_name(user=user, company=company)

	return {
		"user": user,
		"access": access,
		"mobile_app_profile": profile_name,
		"profile_context": get_profile_context(user=user, company=company) if profile_name else None,
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
