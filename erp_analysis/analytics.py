"""Generic mobile analytics APIs (Phase D)."""

from __future__ import annotations

from typing import Any, Optional

import frappe

from erp_analysis.access_context import guard_mobile_api
from erp_analysis.services.analytics_dimensions import (
	get_effective_dimension_values,
	list_effective_dimensions,
)
from erp_analysis.utils.rpc import clean_kwargs, get_arg, to_int


def _guard_sales_analytics(company: Optional[str] = None) -> dict[str, Any]:
	return guard_mobile_api(
		company=company,
		module_key="sales",
		object_key="erp_analysis.sales_kpis.get_dashboard_kpis",
		scope_module="sales",
	)


@frappe.whitelist(methods=["GET", "POST"])
def get_dimensions(company: Optional[str] = None, **kwargs):
	"""Return authorized logical dimensions for the logged-in user."""
	clean_kwargs(kwargs)
	ctx = _guard_sales_analytics(get_arg("company", company))
	dimensions = list_effective_dimensions(ctx["user"], ctx["company"])
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
	ctx = _guard_sales_analytics(get_arg("company", company))
	dimension = get_arg("dimension", dimension)
	search = get_arg("search", search)
	limit = to_int(get_arg("limit", limit), 50)

	if not dimension:
		frappe.throw(frappe._("dimension is required"), frappe.ValidationError)

	values = get_effective_dimension_values(
		user=ctx["user"],
		company=ctx["company"],
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
	compare: Optional[str] = None,
	**kwargs,
):
	"""Generic sales analysis grouped by a logical dimension."""
	clean_kwargs(kwargs)
	ctx = _guard_sales_analytics(get_arg("company", company))

	from erp_analysis.services.analytics_sales import get_sales_analysis as _impl

	return _impl(
		user=ctx["user"],
		company=ctx["company"],
		from_date=get_arg("from_date", from_date),
		to_date=get_arg("to_date", to_date),
		dimension=get_arg("dimension", dimension),
		secondary_dimension=get_arg("secondary_dimension", secondary_dimension),
		metric=get_arg("metric", metric) or "net_sales",
		filters=get_arg("filters", filters),
		limit=to_int(get_arg("limit", limit), 50),
		order=get_arg("order", order) or "desc",
		compare=get_arg("compare", compare),
	)
