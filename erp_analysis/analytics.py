"""Generic mobile analytics APIs (Phase D)."""

from __future__ import annotations

from typing import Any, Optional

import frappe

from erp_analysis.security import require_authenticated_user
from erp_analysis.services.analytics_dimensions import (
	get_effective_dimension_values,
	list_effective_dimensions,
)
from erp_analysis.utils.rpc import clean_kwargs, get_arg, to_int


def _resolve_company(user: str, company: Optional[str] = None) -> Optional[str]:
	from erp_analysis.api import _get_my_access

	access = _get_my_access(user=user, company=company)
	scope = access.get("scope") or {}
	profile_company = scope.get("company")
	if profile_company:
		if company and company != profile_company:
			frappe.throw(
				frappe._("Company {0} is outside your access scope").format(company),
				frappe.PermissionError,
			)
		return profile_company
	return company or frappe.defaults.get_user_default("Company")


def _require_sales_analytics_access(user: str, company: Optional[str] = None) -> None:
	from erp_analysis.permissions.access_profile import PermissionDenied, _get_user_profile_name, evaluate

	if not _get_user_profile_name(user, company):
		return
	try:
		evaluate(user, company or _resolve_company(user), None, None, "erp_analysis.sales_kpis.get_dashboard_kpis")
	except PermissionDenied as exc:
		frappe.throw(str(exc), frappe.PermissionError)


@frappe.whitelist(methods=["GET", "POST"])
def get_dimensions(company: Optional[str] = None, **kwargs):
	"""Return authorized logical dimensions for the logged-in user."""
	clean_kwargs(kwargs)
	user = require_authenticated_user()
	company = _resolve_company(user, get_arg("company", company))
	_require_sales_analytics_access(user, company)
	dimensions = list_effective_dimensions(user, company)
	return {
		"data": dimensions,
		"meta": {"schema_version": 1, "count": len(dimensions)},
	}


@frappe.whitelist(methods=["GET", "POST"])
def get_dimension_values(
	dimension: Optional[str] = None,
	search: Optional[str] = None,
	limit: Optional[int] = None,
	company: Optional[str] = None,
	**kwargs,
):
	"""Return value/label pairs for a logical dimension."""
	clean_kwargs(kwargs)
	user = require_authenticated_user()
	dimension = get_arg("dimension", dimension)
	search = get_arg("search", search)
	limit = to_int(get_arg("limit", limit), 50)
	company = _resolve_company(user, get_arg("company", company))
	_require_sales_analytics_access(user, company)

	if not dimension:
		frappe.throw(frappe._("dimension is required"), frappe.ValidationError)

	values = get_effective_dimension_values(
		user=user,
		company=company,
		dimension_key=dimension,
		search=search,
		limit=limit,
	)
	return {
		"data": values,
		"meta": {
			"schema_version": 1,
			"dimension": dimension,
			"count": len(values),
		},
	}


@frappe.whitelist(methods=["GET", "POST"])
def get_sales_analysis(
	from_date: Optional[str] = None,
	to_date: Optional[str] = None,
	dimension: Optional[str] = None,
	secondary_dimension: Optional[str] = None,
	metric: Optional[str] = None,
	filters: Any = None,
	limit: Optional[int] = None,
	order: Optional[str] = None,
	company: Optional[str] = None,
	**kwargs,
):
	"""Generic sales analysis grouped by a logical dimension."""
	clean_kwargs(kwargs)
	user = require_authenticated_user()
	company = _resolve_company(user, get_arg("company", company))
	_require_sales_analytics_access(user, company)

	from erp_analysis.services.analytics_sales import get_sales_analysis as _impl

	return _impl(
		user=user,
		company=company,
		from_date=get_arg("from_date", from_date),
		to_date=get_arg("to_date", to_date),
		dimension=get_arg("dimension", dimension),
		secondary_dimension=get_arg("secondary_dimension", secondary_dimension),
		metric=get_arg("metric", metric) or "net_sales",
		filters=get_arg("filters", filters),
		limit=to_int(get_arg("limit", limit), 50),
		order=get_arg("order", order) or "desc",
	)
