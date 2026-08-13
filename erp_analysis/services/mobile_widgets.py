"""Resolve dashboard widget metadata and data for v2 dynamic mobile home."""

from __future__ import annotations

import json
from typing import Any, Optional

import frappe
from frappe import _

from erp_analysis.access_context import guard_mobile_api
from erp_analysis.services.mobile_profile import resolve_mobile_app_profile_name

CHART_WIDGET_TYPES = frozenset({"PIE", "DONUT", "BAR", "LINE", "RANKING"})
LEGACY_WIDGET_TYPES = frozenset({"LIST", "KPI", "TABLE", "MATRIX"})
NAV_WIDGET_TYPES = frozenset({"LINK"})

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


def parse_widget_config_json(raw: Any) -> dict[str, Any]:
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


def resolve_chart_dimension(
	widget: dict[str, Any],
	*,
	dimension_override: Optional[str] = None,
	drill_depth: Optional[int] = None,
) -> tuple[str, dict[str, Any], Optional[int]]:
	"""Pick group-by dimension from override, drill_path index, or widget default."""
	config = widget.get("config") or {}
	drill_path = _normalize_drill_path(config.get("drill_path"))

	if dimension_override:
		dim = dimension_override.strip().lower()
		return dim, config, _depth_for_dimension(dim, drill_path)

	if drill_depth is not None and drill_path:
		idx = int(drill_depth)
		if idx < 0 or idx >= len(drill_path):
			frappe.throw(_("drill_depth {0} is out of range for drill_path").format(idx), frappe.ValidationError)
		return drill_path[idx], config, idx

	default_dim = (widget.get("dimension_key") or "territory").strip().lower()
	return default_dim, config, _depth_for_dimension(default_dim, drill_path)


def next_drill_dimension(current_dimension: str, config: dict[str, Any]) -> Optional[str]:
	drill_path = _normalize_drill_path(config.get("drill_path"))
	if not drill_path:
		return None
	idx = _depth_for_dimension(current_dimension, drill_path)
	if idx is None or idx + 1 >= len(drill_path):
		return None
	return drill_path[idx + 1]


def _normalize_drill_path(raw: Any) -> list[str]:
	if not raw:
		return []
	if isinstance(raw, str):
		raw = [raw]
	if not isinstance(raw, (list, tuple)):
		return []
	return [str(item).strip().lower() for item in raw if str(item).strip()]


def _depth_for_dimension(dimension: str, drill_path: list[str]) -> Optional[int]:
	dim = (dimension or "").strip().lower()
	if not drill_path:
		return None
	try:
		return drill_path.index(dim)
	except ValueError:
		return None


def resolve_widget_action(widget: dict[str, Any]) -> dict[str, Any]:
	"""Navigation action for LINK widgets (config.action or module default)."""
	config = widget.get("config") or {}
	action = config.get("action")
	if isinstance(action, dict) and action.get("type"):
		return action

	widget_type = (widget.get("widget_type") or "").upper()
	module_key = widget.get("module_key")
	if widget_type == "LINK" and module_key:
		target = config.get("target") or "module"
		if target == "dashboard":
			dashboard_id = config.get("dashboard_id") or module_key
			return {
				"type": "navigate",
				"target": "dashboard",
				"dashboard_id": dashboard_id,
			}
		return {
			"type": "navigate",
			"target": "module",
			"route_key": config.get("route_key") or module_key,
			"screen": config.get("screen") or "dashboard",
		}

	frappe.throw(
		_("Widget {0} has no navigation action configured").format(widget.get("key")),
		frappe.ValidationError,
	)


def _resolve_compare_mode(config: dict[str, Any], compare_override: Optional[str] = None) -> Optional[str]:
	if compare_override:
		key = compare_override.strip().lower()
		return key or None
	compare = config.get("compare")
	if not compare:
		return None
	return str(compare).strip().lower() or None


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

	config = row.get("config") or parse_widget_config_json(row.get("config_json"))

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
		"dashboard_id": row.get("dashboard_id"),
		"config": config,
	}
	return merged


def get_dashboard_widget_data(
	user: Optional[str] = None,
	widget_key: Optional[str] = None,
	company: Optional[str] = None,
	from_date: Optional[str] = None,
	to_date: Optional[str] = None,
	limit: int = 10,
	dimension: Optional[str] = None,
	filters: Any = None,
	drill_depth: Optional[int] = None,
	compare: Optional[str] = None,
	**kwargs,
) -> dict[str, Any]:
	"""Return chart series or legacy payload for one bootstrap dashboard widget."""
	user = user or frappe.session.user
	company = company or kwargs.get("company")
	widget_key = widget_key or kwargs.get("widget_key")
	limit = int(kwargs.get("limit") or limit or 10)
	dimension = dimension or kwargs.get("dimension")
	filters = filters if filters is not None else kwargs.get("filters")
	if drill_depth is None and kwargs.get("drill_depth") is not None:
		drill_depth = kwargs.get("drill_depth")
	if drill_depth is not None:
		drill_depth = int(drill_depth)
	compare = compare or kwargs.get("compare")

	widget = resolve_widget_definition(user, widget_key, company=company)
	module_key = widget.get("module_key")
	ctx = guard_mobile_api(
		company=company,
		module_key=module_key,
		scope_module="sales" if module_key in ("sales", "sales_performance", "collection") else module_key,
	)
	company = ctx["company"]
	widget_type = widget["widget_type"]

	if widget_type in NAV_WIDGET_TYPES:
		return _link_widget_payload(widget)

	if widget_type in CHART_WIDGET_TYPES:
		return _chart_widget_payload(
			user,
			company,
			widget,
			from_date,
			to_date,
			limit,
			dimension_override=dimension,
			filters=filters,
			drill_depth=drill_depth,
			compare_override=compare,
		)

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
	*,
	dimension_override: Optional[str] = None,
	filters: Any = None,
	drill_depth: Optional[int] = None,
	compare_override: Optional[str] = None,
) -> dict[str, Any]:
	metric = widget.get("metric_key") or "net_sales"
	dimension, config, resolved_depth = resolve_chart_dimension(
		widget,
		dimension_override=dimension_override,
		drill_depth=drill_depth,
	)
	drill_path = _normalize_drill_path(config.get("drill_path"))
	next_dim = next_drill_dimension(dimension, config)
	compare_mode = _resolve_compare_mode(config, compare_override)

	from erp_analysis.services.analytics_sales import get_sales_analysis

	analysis = get_sales_analysis(
		user=user,
		company=company,
		from_date=from_date,
		to_date=to_date,
		dimension=dimension,
		metric=metric,
		filters=filters,
		limit=limit,
		compare=compare_mode,
	)

	series = []
	for row in analysis.get("data") or []:
		point = {
			"label": row.get("label") or row.get("dimension_value"),
			"value": row.get("metric_value"),
			"dimension_value": row.get("dimension_value"),
		}
		if compare_mode == "ly":
			point["value_ly"] = row.get("metric_value_ly")
			point["change_pct"] = row.get("change_pct")
		series.append(point)

	applied_filters = (analysis.get("meta") or {}).get("filters") or {}

	return {
		"widget_key": widget["key"],
		"widget_type": widget["widget_type"],
		"label": widget.get("label"),
		"chart": {
			"series": series,
			"metric": metric,
			"dimension": dimension,
			"filters": applied_filters,
			"compare": compare_mode,
		},
		"meta": {
			"schema_version": 1,
			**(analysis.get("meta") or {}),
			"render_hint": widget["widget_type"].lower(),
			"drill_path": drill_path or None,
			"drill_depth": resolved_depth,
			"next_dimension": next_dim,
			"drillable": bool(next_dim),
		},
	}


def _link_widget_payload(widget: dict[str, Any]) -> dict[str, Any]:
	action = resolve_widget_action(widget)
	return {
		"widget_key": widget["key"],
		"widget_type": "LINK",
		"label": widget.get("label"),
		"action": action,
		"meta": {
			"schema_version": 1,
			"render_hint": "link",
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
