"""Resolve dashboard widget metadata and data for v2 dynamic mobile home."""

from __future__ import annotations

from typing import Any, Optional

import frappe
from frappe import _

from erp_analysis.access_context import guard_mobile_api
from erp_analysis.services.mobile_profile import resolve_mobile_app_profile_name

CHART_WIDGET_TYPES = frozenset({"PIE", "DONUT", "BAR", "LINE", "RANKING"})
LEGACY_WIDGET_TYPES = frozenset({"LIST", "KPI", "TABLE", "MATRIX"})

# Defaults when Desk row omits metric/dimension/legacy API mapping.
WIDGET_DEFAULTS: dict[str, dict[str, Any]] = {
	"sales_card": {
		"module_key": "sales",
		"metric_key": "net_sales",
		"dimension_key": "territory",
		"legacy_method": "erp_analysis.sales_kpis.get_dashboard_kpis",
	},
	"receivables_card": {
		"module_key": "receivables",
		"legacy_method": "erp_analysis.receivables.get_receivables_dashboard",
	},
	"inventory_card": {
		"module_key": "inventory",
		"legacy_method": "erp_analysis.inventory.get_inventory_snapshot",
	},
	"collection_card": {
		"module_key": "collection",
		"legacy_method": "erp_analysis.collection.get_collection_dashboard",
	},
	"executive_card": {
		"module_key": "executive",
		"legacy_method": "erp_analysis.executive.get_executive_dashboard",
	},
	"orders_card": {
		"module_key": "sales_orders",
		"legacy_method": "erp_analysis.sales_orders.get_order_book_dashboard",
	},
	"exceptions_card": {
		"module_key": "exceptions",
		"legacy_method": "erp_analysis.exceptions.get_management_exceptions",
	},
}


def resolve_widget_definition(
	user: str,
	widget_key: str,
	company: Optional[str] = None,
) -> dict[str, Any]:
	"""Merge Mobile App Profile widget row with code defaults."""
	key = (widget_key or "").strip()
	if not key:
		frappe.throw(_("widget_key is required"), frappe.ValidationError)

	defaults = dict(WIDGET_DEFAULTS.get(key, {}))
	profile_name = resolve_mobile_app_profile_name(user=user, company=company)
	row: dict[str, Any] = {}

	if profile_name:
		from erp_analysis.services.mobile_profile import get_profile_widgets

		for widget in get_profile_widgets(profile_name):
			if (widget.get("key") or "").strip() == key:
				row = widget
				break

	if not row and not defaults:
		frappe.throw(_("Unknown dashboard widget: {0}").format(key), frappe.ValidationError)

	merged = {
		"key": key,
		"label": row.get("label") or defaults.get("label") or key.replace("_", " ").title(),
		"widget_type": (row.get("widget_type") or defaults.get("widget_type") or "LIST").upper(),
		"module_key": row.get("module_key") or defaults.get("module_key"),
		"metric_key": row.get("metric_key") or defaults.get("metric_key"),
		"dimension_key": row.get("dimension_key") or defaults.get("dimension_key"),
		"secondary_dimension_key": row.get("secondary_dimension_key") or defaults.get("secondary_dimension_key"),
		"legacy_method": defaults.get("legacy_method"),
		"size": row.get("size") or "md",
	}
	return merged


def get_dashboard_widget_data(
	user: Optional[str] = None,
	widget_key: Optional[str] = None,
	company: Optional[str] = None,
	from_date: Optional[str] = None,
	to_date: Optional[str] = None,
	limit: int = 10,
	**kwargs,
) -> dict[str, Any]:
	"""Return chart series or legacy payload for one bootstrap dashboard widget."""
	user = user or frappe.session.user
	company = company or kwargs.get("company")
	widget_key = widget_key or kwargs.get("widget_key")
	limit = int(kwargs.get("limit") or limit or 10)

	widget = resolve_widget_definition(user, widget_key, company=company)
	module_key = widget.get("module_key")
	ctx = guard_mobile_api(
		company=company,
		module_key=module_key,
		scope_module="sales" if module_key in ("sales", "sales_performance", "collection") else module_key,
	)
	company = ctx["company"]
	widget_type = widget["widget_type"]

	if widget_type in CHART_WIDGET_TYPES:
		return _chart_widget_payload(user, company, widget, from_date, to_date, limit)

	if widget_type == "MATRIX":
		frappe.throw(
			_("MATRIX widgets require secondary_dimension (not supported in v1 widget data API yet)"),
			frappe.ValidationError,
		)

	return _legacy_widget_payload(user, company, widget, from_date, to_date, limit, kwargs)


def _chart_widget_payload(
	user: str,
	company: Optional[str],
	widget: dict[str, Any],
	from_date: Optional[str],
	to_date: Optional[str],
	limit: int,
) -> dict[str, Any]:
	metric = widget.get("metric_key") or "net_sales"
	dimension = widget.get("dimension_key") or "territory"

	from erp_analysis.services.analytics_sales import get_sales_analysis

	analysis = get_sales_analysis(
		user=user,
		company=company,
		from_date=from_date,
		to_date=to_date,
		dimension=dimension,
		metric=metric,
		limit=limit,
	)

	series = [
		{
			"label": row.get("label") or row.get("dimension_value"),
			"value": row.get("metric_value"),
		}
		for row in analysis.get("data") or []
	]

	return {
		"widget_key": widget["key"],
		"widget_type": widget["widget_type"],
		"label": widget.get("label"),
		"chart": {
			"series": series,
			"metric": metric,
			"dimension": dimension,
		},
		"meta": {
			"schema_version": 1,
			**(analysis.get("meta") or {}),
			"render_hint": widget["widget_type"].lower(),
		},
	}


def _legacy_widget_payload(
	user: str,
	company: Optional[str],
	widget: dict[str, Any],
	from_date: Optional[str],
	to_date: Optional[str],
	limit: int,
	extra: dict[str, Any],
) -> dict[str, Any]:
	method_path = widget.get("legacy_method")
	if not method_path:
		frappe.throw(
			_("Widget {0} has no legacy API mapping").format(widget["key"]),
			frappe.ValidationError,
		)

	method = frappe.get_attr(method_path)
	call_kwargs: dict[str, Any] = {}
	if company:
		call_kwargs["company"] = company
	if from_date:
		call_kwargs["from_date"] = from_date
	if to_date:
		call_kwargs["to_date"] = to_date
	if limit:
		call_kwargs["limit"] = limit
	payload = method(**call_kwargs)

	return {
		"widget_key": widget["key"],
		"widget_type": widget.get("widget_type") or "LIST",
		"label": widget.get("label"),
		"data": payload,
		"meta": {
			"schema_version": 1,
			"legacy_method": method_path,
			"render_hint": "list",
		},
	}
