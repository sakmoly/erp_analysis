"""Resolve dashboard widget metadata and data for v2 dynamic mobile home."""

from __future__ import annotations

import inspect
import json
from datetime import datetime
from typing import Any, Optional

import frappe
from frappe import _

from erp_analysis.access_context import get_effective_company, guard_mobile_api, has_module_access
from erp_analysis.fixtures.shell_module_dashboards import resolve_dashboard_board_id
from erp_analysis.services.mobile_profile import get_profile_widgets, resolve_mobile_app_profile_name
from erp_analysis.services.widget_batch_cache import (
	get_cached_kpi,
	reset_batch_kpi_cache,
	set_cached_kpi,
)

CHART_WIDGET_TYPES = frozenset({"PIE", "DONUT", "BAR", "LINE"})
TABLE_WIDGET_TYPES = frozenset({"TABLE", "RANKING"})
LEGACY_WIDGET_TYPES = frozenset({"LIST", "MATRIX"})
NAV_WIDGET_TYPES = frozenset({"LINK"})

BOARD_DATA_CACHE_TTL = 180
BOARD_DATA_CACHE_VERSION = 37
LEGACY_WIDGET_CACHE_TTL = 120
LEGACY_WIDGET_CACHE_VERSION = 1
_LEGACY_WIDGET_CACHE_KEYS = frozenset(
	{
		"home_quick_insights",
		"home_recent_activities",
		"home_trend_overview",
	}
)

# Mobile clients cache board JSON locally; bump when KPI semantics change.
BOARD_DATA_REVISION = 4


def _effective_widget_row_limit(widget: dict[str, Any], limit: int) -> int:
	"""Profile row_limit wins over request limit (e.g. salesperson top 10)."""
	config = widget.get("config") or {}
	defaults = WIDGET_DEFAULTS.get(widget.get("key") or "", {})
	default_limit = (defaults.get("config") or {}).get("row_limit")
	configured = config.get("row_limit", default_limit)
	if configured is not None and str(configured).strip() != "":
		return max(int(configured), int(limit or 0))
	return int(limit or 10)

# Optional lookup aliases (mobile may request batch data by alias or kpi_id).
WIDGET_KEY_ALIASES: dict[str, str] = {
	"sales_by_channel": "sales_by_division",
	"sales_donut_channel": "sales_donut_division",
	"channel_ranking": "sales_by_division",
	"sales_channel_ranking": "sales_by_division",
	"sales_by_channel_pie": "sales_donut_division",
	"channel_donut": "sales_donut_division",
}

RANKING_WIDGET_ALIASES: dict[str, list[str]] = {
	"sales_by_salesperson": ["top_salespersons", "salesperson_ranking"],
	"sales_by_territory": ["sales_dash_territory", "territory_ranking"],
	"sales_by_customer_group": ["customer_group_ranking"],
	"sales_by_division": ["sales_by_channel", "channel_ranking", "sales_channel_ranking"],
}

DONUT_WIDGET_ALIASES: dict[str, list[str]] = {
	"sales_donut_customer_group": ["sales_by_customer_group_pie"],
	"sales_donut_division": ["sales_donut_channel", "sales_by_channel_pie", "channel_donut"],
}
KPI_WIDGET_ALIASES: dict[str, list[str]] = {
	"home_total_sales_kpi": ["total_sales_kpi", "sales_ytd_kpi", "net_sales_kpi"],
	"home_total_receivables_kpi": ["total_receivables_kpi", "receivables_total_kpi"],
	"home_total_inventory_kpi": ["total_inventory_kpi", "inventory_value_kpi"],
	"home_total_purchases_kpi": ["total_purchases_kpi", "purchases_ytd_kpi"],
	"home_total_payables_kpi": ["total_payables_kpi", "payables_total_kpi"],
	"home_gross_profit_kpi": ["gross_profit_kpi", "gp_ytd_kpi"],
	"home_gp_margin_kpi": ["gp_margin_kpi", "gross_profit_margin_kpi"],
	"home_current_ratio_kpi": ["current_ratio_kpi"],
	"home_operating_cash_flow_kpi": ["operating_cash_flow_kpi", "cash_flow_kpi"],
	"home_net_profit_kpi": ["net_profit_kpi"],
	"home_sales_health": ["sales_performance_health", "sales_health_score"],
	"home_receivables_health": ["receivables_health_score"],
	"home_inventory_health": ["inventory_health_score"],
	"home_payables_health": ["payables_health_score"],
	"sales_total_kpi": ["sales_dash_net_ytd_kpi", "net_sales_kpi"],
	"sales_cogs_kpi": ["cogs_kpi", "cost_of_goods_sold_kpi"],
	"sales_gp_kpi": ["gross_profit_kpi", "sales_gross_profit_kpi"],
	"sales_gp_margin_kpi": ["gross_profit_margin_kpi", "gp_margin_kpi"],
	"sales_active_customers_kpi": ["active_customers_kpi", "customer_count_kpi"],
	"sales_returns_kpi": ["returns_kpi", "sales_return_kpi"],
	"sales_orders_kpi": ["total_orders_kpi", "total_orders"],
}

CHART_WIDGET_ALIASES: dict[str, list[str]] = {
	"sales_trend_line": ["sales_overview_trend", "sales_trend_chart"],
}

_SALES_OVERVIEW_DASHBOARD_KPI_KEYS = frozenset(
	{"sales_total_kpi", "sales_dash_net_ytd_kpi", "net_sales_kpi"}
)

# Sales Overview board: honour filter bar (territory) via analytics_sales.get_sales_kpi.
_SALES_OVERVIEW_ANALYTICS_METRICS = frozenset(
	{
		"gross_profit",
		"gp_pct",
		"gross_profit_pct",
		"cogs",
		"sales_return",
		"discount_amount",
		"customer_count",
		"active_customers",
		"transactions",
		"average_transaction",
	}
)


def _board_filters_have_scope(filters: Any) -> bool:
	from erp_analysis.services.analytics_dimensions import parse_logical_filters

	parsed = parse_logical_filters(filters)
	if parsed.get("territory"):
		return True
	return bool(parsed)


def _uses_filter_aware_sales_kpi(widget: dict[str, Any], metric: str, filters: Any) -> bool:
	"""Use get_sales_kpi when the board filter bar scopes territory (Home + Sales Overview)."""
	metric = (metric or "").strip().lower()
	if metric not in _SALES_OVERVIEW_ANALYTICS_METRICS:
		return False
	board = (widget.get("dashboard_id") or "").strip()
	if board == "sales_overview":
		return True
	if board == "home" and _board_filters_have_scope(filters):
		return True
	return False


def _build_canonical_widget_key_map() -> dict[str, str]:
	"""Map alias / kpi_id keys → canonical profile widget_key."""
	out: dict[str, str] = dict(WIDGET_KEY_ALIASES)
	for groups in (KPI_WIDGET_ALIASES, RANKING_WIDGET_ALIASES, DONUT_WIDGET_ALIASES, CHART_WIDGET_ALIASES):
		for canonical, aliases in groups.items():
			out[canonical] = canonical
			for alias in aliases or []:
				alias_key = str(alias).strip()
				if alias_key:
					out[alias_key] = canonical
	return out


CANONICAL_WIDGET_KEYS = _build_canonical_widget_key_map()


def _canonical_widget_key(key: str) -> str:
	key = (key or "").strip()
	if not key:
		return key
	return CANONICAL_WIDGET_KEYS.get(key, key)


def _uses_dashboard_sales_kpi(
	widget: dict[str, Any],
	config: dict[str, Any],
	*,
	user: str,
	company: Optional[str],
	filters: Any = None,
) -> bool:
	from erp_analysis.services.analytics_sales import company_wide_sales_view_for_filters

	if company_wide_sales_view_for_filters(user, company, filters):
		return False
	if _widget_data_source(config) == "dashboard":
		return True
	if not frappe.db.table_exists("SalesDashBoard"):
		return False
	key = _canonical_widget_key(widget.get("key") or "")
	board = (widget.get("dashboard_id") or "").strip()
	metric = (widget.get("metric_key") or "").strip().lower()
	if metric and metric != "net_sales":
		return False
	if key in _SALES_OVERVIEW_DASHBOARD_KPI_KEYS:
		return board in ("", "sales_overview")
	return False


def _register_receivables_territory_aliases(widgets_out: dict[str, Any], payload: dict[str, Any]) -> None:
	"""Register one slim KPI payload per territory for mobile batch lookup."""
	for kpi in payload.get("kpis") or []:
		if not isinstance(kpi, dict):
			continue
		kpi_id = str(kpi.get("kpi_id") or kpi.get("label") or "").strip()
		if not kpi_id:
			continue
		value = kpi.get("value")
		widgets_out[kpi_id] = {
			**payload,
			"widget_key": payload.get("widget_key"),
			"widget_type": "KPI",
			"label": kpi_id,
			"kpis": [kpi],
			"kpi": {
				**kpi,
				"show_currency_symbol": True,
			},
			"value": value,
			"data": {
				"value": value,
				"kpi_id": kpi_id,
				"format": kpi.get("format") or "currency_compact",
			},
		}


def _register_widget_payload_aliases(
	widgets_out: dict[str, Any],
	widget: dict[str, Any],
	payload: dict[str, Any],
) -> None:
	"""Duplicate KPI payloads under kpi_id / alias keys for mobile lookup."""
	key = widget["key"]
	widgets_out[key] = payload
	config = widget.get("config") or {}

	if payload.get("widget_type") == "KPI":
		kpi_id = (config.get("kpi_id") or payload.get("kpi", {}).get("kpi_id") or key).strip()
		# Avoid a second board tile when kpi_id differs from widget_key but label matches (native dedupes poorly).
		if kpi_id and kpi_id != key:
			widgets_out[kpi_id] = payload
		for alias in KPI_WIDGET_ALIASES.get(key, []):
			alias_key = str(alias).strip()
			if alias_key:
				widgets_out[alias_key] = payload
		return

	for alias in CHART_WIDGET_ALIASES.get(key, []):
		alias_key = str(alias).strip()
		if alias_key:
			widgets_out[alias_key] = payload

	if payload.get("widget_type") == "RANKING":
		for alias in RANKING_WIDGET_ALIASES.get(key, []):
			alias_key = str(alias).strip()
			if alias_key:
				widgets_out[alias_key] = payload

	if payload.get("widget_type") == "DONUT":
		for alias in DONUT_WIDGET_ALIASES.get(key, []):
			alias_key = str(alias).strip()
			if alias_key:
				widgets_out[alias_key] = payload

	kpi_id = config.get("kpi_id")
	if kpi_id and payload.get("widget_type") == "KPI":
		widgets_out[str(kpi_id).strip()] = payload
	chart_key = config.get("chart_key") or (payload.get("meta") or {}).get("chart_key")
	if chart_key and payload.get("widget_type") in CHART_WIDGET_TYPES:
		widgets_out[str(chart_key).strip()] = payload


# Defaults when Desk row omits metric/dimension/legacy API mapping.
WIDGET_DEFAULTS: dict[str, dict[str, Any]] = {
	"sales_card": {
		"module_key": "sales",
		"metric_key": "net_sales",
		"dimension_key": "territory",
		"widget_type": "PIE",
	},
	"receivables_card": {
		"module_key": "receivables",
		"widget_type": "PIE",
		"metric_key": "outstanding",
		"dimension_key": "territory",
		"legacy_method": "erp_analysis.receivables.get_receivables_dashboard",
		"config": {
			"payload_source": "legacy_chart",
			"rows_key": "territory_totals",
			"label_field": "territory",
			"value_field": "outstanding",
			"section_title": "Receivables Card",
			"row_group": "receivables_card",
		},
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
	"sales_dash_order_book": {
		"module_key": "sales_orders",
		"legacy_method": "erp_analysis.sales_orders.get_order_book_dashboard",
	},
	"sales_dash_gross_profit": {
		"module_key": "profitability",
		"legacy_method": "erp_analysis.profitability.get_gross_profit_dashboard",
	},
	"sales_dash_exceptions": {
		"module_key": "exceptions",
		"legacy_method": "erp_analysis.exceptions.get_management_exceptions",
	},
	"receivables_dash_card": {
		"module_key": "receivables",
		"legacy_method": "erp_analysis.receivables.get_receivables_dashboard",
	},
	"receivables_total_kpi": {
		"module_key": "receivables",
		"metric_key": "total_receivable",
		"widget_type": "KPI",
	},
	"receivables_overdue_kpi": {
		"module_key": "receivables",
		"metric_key": "overdue",
		"widget_type": "KPI",
	},
	"receivables_current_kpi": {
		"module_key": "receivables",
		"metric_key": "current",
		"widget_type": "KPI",
	},
	"receivables_overdue_pct_kpi": {
		"module_key": "receivables",
		"metric_key": "overdue_pct",
		"widget_type": "KPI",
	},
	"receivables_customer_count_kpi": {
		"module_key": "receivables",
		"metric_key": "customer_count",
		"widget_type": "KPI",
	},
	"inventory_dash_card": {
		"module_key": "inventory",
		"legacy_method": "erp_analysis.inventory.get_inventory_snapshot",
	},
	"collection_dash_card": {
		"module_key": "collection",
		"legacy_method": "erp_analysis.collection.get_collection_dashboard",
	},
	"executive_dash_card": {
		"module_key": "executive",
		"legacy_method": "erp_analysis.executive.get_executive_dashboard",
	},
	"sales_by_salesperson": {
		"module_key": "sales",
		"metric_key": "net_sales",
		"dimension_key": "salesperson",
		"widget_type": "RANKING",
		"period": "ytd",
		"config": {
			"compare": "ly",
			"section_title": "Sales By",
			"row_limit": 10,
		},
	},
	"sales_by_territory": {
		"module_key": "sales",
		"metric_key": "net_sales",
		"dimension_key": "territory",
		"widget_type": "RANKING",
		"period": "ytd",
		"config": {
			"compare": "ly",
			"section_title": "Sales By",
			"row_limit": 5,
		},
	},
	"sales_management_attention": {
		"module_key": "sales",
		"widget_type": "LIST",
		"period": "ytd",
		"config": {
			"data_source": "attention",
			"section": "all",
			"section_title": "Management Attention",
			"format": "currency_compact",
			"row_limit": 4,
		},
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


def _period_from_widget(widget: dict[str, Any], config: Optional[dict[str, Any]] = None) -> str:
	config = config or widget.get("config") or {}
	raw = widget.get("period") or config.get("period") or "mtd"
	return str(raw).strip().lower() or "mtd"


def _compare_from_widget(
	widget: dict[str, Any],
	config: Optional[dict[str, Any]] = None,
	compare_override: Optional[str] = None,
) -> Optional[str]:
	if compare_override:
		key = compare_override.strip().lower()
		return key or None
	config = config or widget.get("config") or {}
	if widget.get("show_ly"):
		return "ly"
	compare = config.get("compare")
	if not compare:
		return None
	return str(compare).strip().lower() or None


def _filters_cache_key(filters: Any) -> str:
	if filters is None:
		return ""
	if isinstance(filters, str):
		return filters
	try:
		return json.dumps(filters, sort_keys=True, default=str)
	except Exception:
		return str(filters)


_TERRITORY_ALL_SENTINELS = frozenset({"", "all", "all territories", "all territory", "any"})


def _clean_territory_filter_values(values: list[Any]) -> list[str]:
	cleaned: list[str] = []
	for value in values or []:
		text = str(value or "").strip()
		if not text or text.lower() in _TERRITORY_ALL_SENTINELS:
			continue
		cleaned.append(text)
	return cleaned


def _known_division_values(company: Optional[str] = None) -> set[str]:
	cache_key = f"mobile_division_values:{company or ''}"
	cached = frappe.cache().get_value(cache_key)
	if cached is not None:
		return set(cached)
	names: set[str] = set()
	if frappe.db.table_exists("SalesDashBoard") and frappe.db.has_column("SalesDashBoard", "Division"):
		rows = frappe.db.sql(
			"""
			SELECT DISTINCT COALESCE(`Division`, '') AS division
			FROM `tabSalesDashBoard`
			WHERE COALESCE(`Division`, '') != ''
			""",
			as_dict=True,
		)
		names = {str(r.get("division") or "").strip() for r in rows if str(r.get("division") or "").strip()}
	frappe.cache().set_value(cache_key, list(names), expires_in_sec=3600)
	return names


def _parse_drill_stack(raw: Any) -> dict[str, list[Any]]:
	"""Mobile drill breadcrumbs: [{dimension, value|label}, ...]."""
	from erp_analysis.services.analytics_dimensions import DIMENSION_KEY_ALIASES

	if raw is None or raw == "":
		return {}
	if isinstance(raw, str):
		try:
			raw = json.loads(raw)
		except Exception:
			return {}
	if not isinstance(raw, (list, tuple)):
		return {}
	out: dict[str, list[Any]] = {}
	for entry in raw:
		if not isinstance(entry, dict):
			continue
		dim = (entry.get("dimension") or entry.get("key") or "").strip().lower()
		dim = DIMENSION_KEY_ALIASES.get(dim, dim)
		val = entry.get("value") or entry.get("label") or entry.get("name")
		if not dim or val is None or not str(val).strip():
			continue
		out.setdefault(dim, [])
		text = str(val).strip()
		if text not in out[dim]:
			out[dim].append(text)
	return out


def _drill_crumbs_length(kwargs: dict[str, Any]) -> int:
	from erp_analysis.utils.rpc import get_arg

	raw = get_arg("drill_crumbs", kwargs.get("drill_crumbs"))
	if raw is None or raw == "":
		raw = get_arg("crumbs", kwargs.get("crumbs"))
	if raw is None or raw == "":
		return 0
	if isinstance(raw, str):
		try:
			raw = json.loads(raw)
		except Exception:
			return 0
	if isinstance(raw, (list, tuple)):
		return len([e for e in raw if isinstance(e, dict)])
	return 0


def _resolve_effective_drill_depth(
	widget: dict[str, Any],
	*,
	drill_depth: Optional[int],
	dimension: Optional[str],
	parsed: Optional[dict[str, list[Any]]],
	kwargs: dict[str, Any],
) -> Optional[int]:
	"""Infer drill depth when mobile sends `dimension` or crumbs but omits drill_depth."""
	from erp_analysis.services.analytics_dimensions import DIMENSION_KEY_ALIASES

	config = widget.get("config") or {}
	drill_path = _normalize_drill_path(config.get("drill_path"))
	if not drill_path:
		return int(drill_depth) if drill_depth is not None else None

	if drill_depth is not None:
		return int(drill_depth)

	candidates: list[int] = []
	crumbs_len = _drill_crumbs_length(kwargs)
	if crumbs_len > 0:
		candidates.append(crumbs_len)

	out = dict(parsed or {})
	for stack_key in ("drill_stack", "filter_stack", "drill_crumbs", "crumbs", "breadcrumb"):
		for key, values in _parse_drill_stack(kwargs.get(stack_key) or frappe.form_dict.get(stack_key)).items():
			if values:
				out.setdefault(key, [])
				for val in values:
					if val not in out[key]:
						out[key].append(val)

	if not out.get("sub_group") and out.get("item_group"):
		out["sub_group"] = list(out["item_group"])

	prefix_depth = 0
	for path_dim in drill_path:
		key = DIMENSION_KEY_ALIASES.get(path_dim, path_dim)
		if out.get(key):
			prefix_depth += 1
		else:
			break
	if prefix_depth > 0:
		candidates.append(prefix_depth)

	dim = (dimension or "").strip().lower()
	if dim:
		dim = DIMENSION_KEY_ALIASES.get(dim, dim)
		idx = _depth_for_dimension(dim, drill_path)
		if idx is not None:
			candidates.append(idx)

	if not candidates:
		return None
	return max(candidates)


def _normalize_drill_filters(
	user: str,
	company: Optional[str],
	*,
	widget: dict[str, Any],
	drill_depth: Optional[int],
	dimension: Optional[str],
	parsed: Optional[dict[str, list[Any]]],
	kwargs: dict[str, Any],
) -> tuple[Optional[dict[str, list[Any]]], bool]:
	"""
	Apply drill_path parent filters; refuse unscoped sub_group under division drill.
	Returns (filters, drill_scope_ok).
	"""
	from erp_analysis.services.analytics_dimensions import DIMENSION_KEY_ALIASES

	config = widget.get("config") or {}
	drill_path = _normalize_drill_path(config.get("drill_path"))
	out = dict(parsed or {})

	if not drill_path:
		return out or None, True

	depth = drill_depth
	if depth is None:
		depth = _resolve_effective_drill_depth(
			widget,
			drill_depth=None,
			dimension=dimension,
			parsed=out,
			kwargs=kwargs,
		)
	if depth is None or int(depth) <= 0:
		return out or None, True

	depth = int(depth)
	dim = (dimension or "").strip().lower()
	if dim:
		dim = DIMENSION_KEY_ALIASES.get(dim, dim)

	for stack_key in ("drill_stack", "filter_stack", "drill_crumbs", "crumbs", "breadcrumb"):
		stack = _parse_drill_stack(kwargs.get(stack_key) or frappe.form_dict.get(stack_key))
		for key, values in stack.items():
			k = DIMENSION_KEY_ALIASES.get((key or "").strip().lower(), (key or "").strip().lower())
			out.setdefault(k, [])
			for val in values:
				if val not in out[k]:
					out[k].append(val)

	if not out.get("division") and out.get("channel"):
		out["division"] = list(out["channel"])

	division_names = _known_division_values(company)
	wrong_keys = ("sub_group", "item_group", "group", "category")
	for key in list(out.keys()):
		k = (key or "").strip().lower()
		if k in wrong_keys or k in division_names:
			for val in list(out.get(key) or []):
				text = str(val or "").strip()
				if text in division_names and text not in (out.get("division") or []):
					out.setdefault("division", []).append(text)
			if k in wrong_keys and out.get("division"):
				remaining = [v for v in out.get(key) or [] if str(v).strip() not in division_names]
				if remaining:
					out[key] = remaining
				else:
					out.pop(key, None)

	for idx in range(min(depth, len(drill_path))):
		parent_dim = DIMENSION_KEY_ALIASES.get(drill_path[idx], drill_path[idx])
		if out.get(parent_dim):
			continue
		from erp_analysis.utils.rpc import get_arg

		raw = get_arg(parent_dim, kwargs.get(parent_dim))
		if raw is not None and str(raw).strip():
			out.setdefault(parent_dim, []).append(str(raw).strip())

	if not out.get("sub_group") and out.get("item_group"):
		out["sub_group"] = list(out["item_group"])

	from erp_analysis.services.analytics_sales import _coalesce_dashboard_filter_keys

	out = _coalesce_dashboard_filter_keys(out)

	missing: list[str] = []
	if drill_path and drill_path[0] == "division" and depth >= 1 and not out.get("division"):
		missing.append("division")
	if (
		drill_path
		and len(drill_path) > 1
		and drill_path[1] in ("sub_group", "item_group")
		and depth >= 2
		and not out.get("sub_group")
	):
		missing.append("sub_group")
	if drill_path and drill_path[0] == "sales_order" and depth >= 2 and not out.get("sales_order"):
		missing.append("sales_order")
	if missing:
		return out or None, False

	return out or None, True


def _merge_drill_filter_kwargs(
	parsed: dict[str, list[Any]],
	kwargs: dict[str, Any],
) -> dict[str, list[Any]]:
	"""Top-level drill params (mobile sometimes omits filters JSON)."""
	from erp_analysis.utils.rpc import get_arg

	out = dict(parsed or {})
	single_keys = (
		"division",
		"channel",
		"territory",
		"brand",
		"sub_group",
		"item_group",
		"salesperson",
		"sales_order",
	)
	for key in single_keys:
		raw = get_arg(key, kwargs.get(key))
		if raw is None:
			continue
		values: list[Any]
		if isinstance(raw, (list, tuple)):
			values = list(raw)
		else:
			text = str(raw).strip()
			if not text:
				continue
			values = [text]
		cleaned = [v for v in values if v is not None and str(v).strip()]
		if not cleaned:
			continue
		out.setdefault(key, [])
		for val in cleaned:
			if val not in out[key]:
				out[key].append(val)
	return out


def _merge_widget_territory_params(
	parsed: dict[str, list[Any]],
	kwargs: dict[str, Any],
) -> dict[str, list[Any]]:
	from erp_analysis.utils.rpc import get_arg

	out = dict(parsed or {})
	territories_param = get_arg("territories", kwargs.get("territories"))
	if territories_param:
		if isinstance(territories_param, str):
			extra = [t.strip() for t in territories_param.split(",") if t.strip()]
		elif isinstance(territories_param, (list, tuple)):
			extra = [str(t).strip() for t in territories_param if t is not None and str(t).strip()]
		else:
			extra = [str(territories_param).strip()]
		out.setdefault("territory", [])
		for item in extra:
			if item not in out["territory"]:
				out["territory"].append(item)

	territory_param = get_arg("territory", kwargs.get("territory"))
	if territory_param is not None:
		text = str(territory_param).strip()
		if text and text.lower() not in _TERRITORY_ALL_SENTINELS:
			out.setdefault("territory", [])
			if text not in out["territory"]:
				out["territory"].append(text)
	return out


def _normalize_territory_filters(
	user: str,
	company: Optional[str],
	parsed: dict[str, list[Any]],
) -> dict[str, list[Any]]:
	from erp_analysis.permissions.access_profile import resolve_territory_scope

	out = dict(parsed or {})
	if "territory" not in out:
		return out

	cleaned = _clean_territory_filter_values(out.get("territory") or [])
	if not cleaned:
		out.pop("territory", None)
		return out

	scoped = resolve_territory_scope(
		requested_list=cleaned,
		user=user,
		company=company,
		purpose="view",
		module="sales",
	)
	out["territory"] = list(scoped) if scoped is not None else cleaned
	return out


def _resolve_board_filters(
	user: str,
	company: Optional[str],
	kwargs: dict[str, Any],
) -> tuple[Any, dict[str, list[Any]]]:
	"""Parse batch `filters` / legacy `territory` param (mobile + PWA)."""
	from erp_analysis.services.analytics_dimensions import (
		normalize_division_slice_filters,
		parse_logical_filters,
		validate_logical_filters,
	)
	from erp_analysis.utils.rpc import get_arg

	raw = get_arg("filters", kwargs.get("filters"))
	territory = get_arg("territory", kwargs.get("territory"))
	if raw is None and territory and str(territory).strip().lower() not in _TERRITORY_ALL_SENTINELS:
		raw = {"territory": [str(territory).strip()]}
	if raw is None and not get_arg("territories", kwargs.get("territories")):
		return None, {}

	parsed = parse_logical_filters(raw) if raw is not None else {}
	parsed = normalize_division_slice_filters(user, company, parsed)
	parsed = _merge_drill_filter_kwargs(parsed, kwargs)
	parsed = _merge_widget_territory_params(parsed, kwargs)
	parsed = _normalize_territory_filters(user, company, parsed)
	if not parsed:
		return None, {}
	validate_logical_filters(user, company, parsed)
	return parsed, parsed


def _resolve_widget_filters(
	user: str,
	company: Optional[str],
	filters: Any,
	kwargs: dict[str, Any],
) -> Any:
	"""Single-widget drill/batch parity: territory params + All Territories sentinels."""
	from erp_analysis.services.analytics_dimensions import (
		normalize_division_slice_filters,
		parse_logical_filters,
		validate_logical_filters,
	)
	from erp_analysis.utils.rpc import get_arg

	raw = filters
	if raw is None:
		raw = get_arg("filters", None) or get_arg("drill_filters", kwargs.get("drill_filters"))
		if raw is None:
			raw = get_arg("logical_filters", kwargs.get("logical_filters"))

	parsed = parse_logical_filters(raw) if raw is not None else {}
	parsed = normalize_division_slice_filters(user, company, parsed)
	from erp_analysis.services.analytics_sales import _coalesce_dashboard_filter_keys

	parsed = _coalesce_dashboard_filter_keys(parsed)
	parsed = _merge_drill_filter_kwargs(parsed, kwargs)
	parsed = _merge_widget_territory_params(parsed, kwargs)
	parsed = _normalize_territory_filters(user, company, parsed)
	if not parsed:
		return None
	validate_logical_filters(user, company, parsed)
	return parsed


def _board_period_from_kwargs(kwargs: dict[str, Any]) -> Optional[str]:
	from erp_analysis.utils.rpc import get_arg

	period = get_arg("period", kwargs.get("period"))
	if not period:
		return None
	return str(period).strip().lower() or None


def _apply_period_to_widget(widget: dict[str, Any], period: Optional[str]) -> dict[str, Any]:
	if not period:
		return widget
	out = dict(widget)
	out["period"] = period
	config = dict(out.get("config") or {})
	config["period"] = period
	out["config"] = config
	return out


def _legacy_extra_from_filters(filters: Any) -> dict[str, Any]:
	from erp_analysis.services.analytics_dimensions import parse_logical_filters

	parsed = parse_logical_filters(filters)
	territories = [
		str(t).strip() for t in (parsed.get("territory") or []) if t is not None and str(t).strip()
	]
	if len(territories) == 1:
		return {"territory": territories[0]}
	return {}


def _single_territory_filter(parsed_filters: dict[str, list[Any]]) -> bool:
	territories = parsed_filters.get("territory") or []
	return len(territories) == 1


def clear_dashboard_board_cache() -> None:
	frappe.cache().delete_keys("mobile_board_data:*")


def _board_data_request_cache_suffix(
	user: str,
	company: Optional[str],
	kwargs: dict[str, Any],
	*,
	batch_compare: Optional[str],
) -> str:
	"""Distinct Redis board payloads by compare mode and sales view scope."""
	from erp_analysis.utils.rpc import to_bool

	from erp_analysis.permissions.access_profile import get_view_overrides

	show_ly = to_bool(kwargs.get("show_ly"), False)
	compare = (kwargs.get("compare") or batch_compare or "").strip().lower()
	if show_ly and not compare:
		compare = "ly"
	view_all = 0
	try:
		flags = get_view_overrides(user, company)
		if flags.get("allow_view_all_sales"):
			view_all = 1
	except Exception:
		pass
	return f"ly:{int(show_ly)}:cmp:{compare or '-'}:va:{view_all}"


def _warm_board_kpi_cache(
	user: str,
	company: Optional[str],
	widgets: list[dict[str, Any]],
	*,
	board_period: Optional[str],
	batch_compare: Optional[str],
	filters: Any,
	filters_key: str,
	from_date: Optional[str],
	to_date: Optional[str],
) -> None:
	"""Pre-fetch KPI payloads for this board (period + compare + filters aware)."""
	from erp_analysis.access_context import has_module_access
	from erp_analysis.services.kpi.home_metrics import get_home_kpi, is_home_kpi
	from erp_analysis.services.module_kpis import get_module_kpi, is_module_kpi

	for widget in widgets:
		if (widget.get("widget_type") or "").upper() != "KPI":
			continue
		widget_for_build = _apply_period_to_widget(widget, board_period)
		config = widget_for_build.get("config") or {}
		metric = (widget_for_build.get("metric_key") or "net_sales").strip().lower()
		module_key = (widget_for_build.get("module_key") or "").strip().lower()
		period = _period_from_widget(widget_for_build, config)
		compare = _compare_from_widget(widget_for_build, config, batch_compare)
		if not module_key or not metric:
			continue
		if not has_module_access(module_key, user=user, company=company):
			continue

		is_gauge = _is_health_gauge_widget(widget_for_build, config, metric)
		use_dashboard_kpi = _uses_dashboard_sales_kpi(
			widget_for_build, config, user=user, company=company, filters=filters
		)
		cache_metric = f"{module_key}:{metric}" if module_key != "sales" else metric
		if use_dashboard_kpi:
			cache_metric = f"dashboard:{metric}"
		if is_gauge:
			cache_metric = f"health:{module_key}:{widget_for_build.get('key')}"

		if get_cached_kpi(company, cache_metric, period, compare, filters_key) is not None:
			continue

		try:
			if use_dashboard_kpi:
				from erp_analysis.services.analytics_sales import get_dashboard_sales_kpi

				kpi = get_dashboard_sales_kpi(
					user=user,
					company=company,
					metric=metric,
					from_date=from_date,
					to_date=to_date,
					period=period,
					filters=filters_key,
					compare=compare,
				)
			elif is_gauge or is_home_kpi(metric):
				kpi = get_home_kpi(
					user=user,
					company=company,
					metric_key=metric,
					module_key=module_key,
					widget_key=widget_for_build.get("key") or "",
					period=period,
					compare=compare,
					from_date=from_date,
					to_date=to_date,
				)
			elif is_module_kpi(module_key, metric):
				kpi = get_module_kpi(
					user=user,
					company=company,
					module_key=module_key,
					metric_key=metric,
					period=period,
					filters=filters_key,
				)
			else:
				continue
		except Exception:
			frappe.log_error(
				title=f"warm_board_kpi.{widget_for_build.get('key')}",
				message=frappe.get_traceback(),
			)
			continue
		set_cached_kpi(company, cache_metric, period, compare, filters_key, kpi)


def resolve_chart_dimension(
	widget: dict[str, Any],
	*,
	dimension_override: Optional[str] = None,
	drill_depth: Optional[int] = None,
) -> tuple[str, dict[str, Any], Optional[int]]:
	"""Pick group-by dimension from override, drill_path index, or widget default."""
	from erp_analysis.services.analytics_dimensions import DIMENSION_KEY_ALIASES

	config = widget.get("config") or {}
	drill_path = _normalize_drill_path(config.get("drill_path"))

	def _norm_dim(raw: Optional[str]) -> Optional[str]:
		if not raw:
			return None
		key = raw.strip().lower()
		return DIMENSION_KEY_ALIASES.get(key, key)

	# Prefer drill_path index when set — mobile often keeps a stale `dimension` from the prior step.
	if drill_depth is not None and drill_path:
		idx = int(drill_depth)
		if idx < 0 or idx >= len(drill_path):
			frappe.throw(_("drill_depth {0} is out of range for drill_path").format(idx), frappe.ValidationError)
		path_dim = drill_path[idx]
		override = _norm_dim(dimension_override)
		if override and override == path_dim:
			return override, config, idx
		return path_dim, config, idx

	if dimension_override:
		dim = _norm_dim(dimension_override)
		if not dim:
			frappe.throw(_("Dimension is required"), frappe.ValidationError)
		return dim, config, _depth_for_dimension(dim, drill_path)

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


def _resolve_effective_view(
	widget: dict[str, Any],
	*,
	drill_depth: Optional[int] = None,
	dimension_override: Optional[str] = None,
) -> str:
	config = widget.get("config") or {}
	widget_type = (widget.get("widget_type") or "LIST").upper()
	drill_path = _normalize_drill_path(config.get("drill_path"))
	drill_views = config.get("drill_views") or {}

	depth = drill_depth
	if dimension_override and drill_path:
		depth = _depth_for_dimension(dimension_override, drill_path)
	elif depth is None and drill_path:
		depth = 0

	if drill_views and depth is not None:
		view = drill_views.get(str(depth))
		if view is None:
			view = drill_views.get(depth)
		if view:
			return str(view).strip().lower()

	if widget_type in TABLE_WIDGET_TYPES:
		return "table"
	if widget_type in CHART_WIDGET_TYPES:
		return widget_type.lower()
	return widget_type.lower()


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


def _merge_widget_definition(key: str, row: dict[str, Any]) -> dict[str, Any]:
	defaults = dict(WIDGET_DEFAULTS.get(key, {}))
	default_config = dict(defaults.get("config") or {})
	row_config = parse_widget_config_json(row.get("config_json")) or row.get("config") or {}
	config = {**default_config, **row_config}
	return {
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
		"period": row.get("period"),
		"show_ly": row.get("show_ly"),
		"show_currency_symbol": row.get("show_currency_symbol"),
		"table_columns_json": row.get("table_columns_json"),
		"config": config,
	}


def resolve_widget_definition(
	user: str,
	widget_key: str,
	company: Optional[str] = None,
) -> dict[str, Any]:
	"""Merge Mobile App Profile widget row with code defaults."""
	requested_key = (widget_key or "").strip()
	if not requested_key:
		frappe.throw(_("widget_key is required"), frappe.ValidationError)
	canonical_key = _canonical_widget_key(requested_key)

	profile_name = resolve_mobile_app_profile_name(user=user, company=company)
	row: dict[str, Any] = {}

	if profile_name:
		from erp_analysis.services.mobile_profile import get_profile_widgets

		for widget in get_profile_widgets(profile_name):
			if (widget.get("key") or "").strip() == canonical_key:
				row = widget
				break

	if not row and canonical_key not in WIDGET_DEFAULTS:
		frappe.throw(_("Unknown dashboard widget: {0}").format(requested_key), frappe.ValidationError)

	merged = _merge_widget_definition(canonical_key, row)
	if requested_key != canonical_key:
		merged["key"] = requested_key
		merged["requested_key"] = requested_key
		merged["canonical_key"] = canonical_key
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
	"""Return chart/table/KPI or legacy payload for one bootstrap dashboard widget."""
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
	board_period = _board_period_from_kwargs(kwargs)
	if board_period:
		widget = _apply_period_to_widget(widget, board_period)
	module_key = widget.get("module_key")
	if (widget.get("key") or "") in (
		"sales_orders_kpi",
		"sales_open_orders_list",
		"total_orders_kpi",
		"total_orders",
	):
		module_key = "sales"
	ctx = guard_mobile_api(
		company=company,
		module_key=module_key,
		scope_module="sales"
		if module_key in ("sales", "sales_performance", "collection", "sales_orders", "sales_order")
		else module_key,
	)
	company = ctx["company"]
	filters = _resolve_widget_filters(user, company, filters, kwargs)
	parsed_filters = filters if isinstance(filters, dict) else {}
	if drill_depth is None:
		inferred = _resolve_effective_drill_depth(
			widget,
			drill_depth=None,
			dimension=dimension,
			parsed=parsed_filters,
			kwargs=kwargs,
		)
		if inferred is not None:
			drill_depth = inferred
	filters, drill_scope_ok = _normalize_drill_filters(
		user,
		company,
		widget=widget,
		drill_depth=drill_depth,
		dimension=dimension,
		parsed=parsed_filters,
		kwargs=kwargs,
	)
	if filters:
		from erp_analysis.services.analytics_dimensions import validate_logical_filters

		validate_logical_filters(user, company, filters)

	reset_batch_kpi_cache()
	return _build_widget_payload(
		user,
		company,
		widget,
		from_date=from_date,
		to_date=to_date,
		limit=limit,
		dimension_override=dimension,
		filters=filters,
		drill_depth=drill_depth,
		compare_override=compare,
		extra={**kwargs, "_drill_scope_ok": drill_scope_ok},
	)


def get_dashboard_board_data(
	user: Optional[str] = None,
	dashboard_id: Optional[str] = None,
	company: Optional[str] = None,
	from_date: Optional[str] = None,
	to_date: Optional[str] = None,
	limit: int = 10,
	use_cache: bool = True,
	refresh: bool = False,
	**kwargs,
) -> dict[str, Any]:
	"""Load all widgets for one dashboard board in a single request."""
	user = user or frappe.session.user
	requested_dashboard_id = (dashboard_id or kwargs.get("dashboard_id") or "home").strip()
	dashboard_id = resolve_dashboard_board_id(requested_dashboard_id)
	limit = int(kwargs.get("limit") or limit or 10)
	from erp_analysis.utils.rpc import to_bool

	use_cache = to_bool(kwargs.get("use_cache", use_cache), True)
	refresh = to_bool(kwargs.get("refresh", refresh), False)

	profile_name = resolve_mobile_app_profile_name(user=user, company=company)
	if not profile_name:
		frappe.throw(_("No mobile profile configured for user"), frappe.ValidationError)

	profile_modified = frappe.db.get_value("Mobile App Profile", profile_name, "modified")
	raw_widgets = get_profile_widgets(profile_name, dashboard_id=dashboard_id)
	if not raw_widgets:
		frappe.throw(
			_("No widgets configured for dashboard {0}").format(dashboard_id),
			frappe.ValidationError,
		)

	ctx = guard_mobile_api(company=company)
	user = ctx["user"]
	company = ctx["company"]

	resolved_widgets: list[dict[str, Any]] = []
	for row in raw_widgets:
		key = (row.get("key") or "").strip()
		if not key:
			continue
		widget = _merge_widget_definition(key, row)
		module_key = widget.get("module_key")
		if module_key and not has_module_access(module_key, user=user, company=company):
			continue
		if (widget.get("config") or {}).get("hidden_on_board"):
			continue
		resolved_widgets.append(widget)

	if not resolved_widgets:
		frappe.throw(
			_("No accessible widgets for dashboard {0}").format(dashboard_id),
			frappe.ValidationError,
		)

	from erp_analysis.api import _get_my_access

	access = _get_my_access(user=user, company=company)
	effective_company = get_effective_company(user=user, requested=company, access=access)

	board_filters, parsed_filters = _resolve_board_filters(user, effective_company, kwargs)
	board_period = _board_period_from_kwargs(kwargs)
	filters_key = _filters_cache_key(board_filters)

	show_ly = to_bool(kwargs.get("show_ly"), False)
	batch_compare = kwargs.get("compare")
	if batch_compare is None and show_ly:
		batch_compare = "ly"
	request_suffix = _board_data_request_cache_suffix(
		user, effective_company, kwargs, batch_compare=batch_compare
	)

	cache_key = (
		f"mobile_board_data:v{BOARD_DATA_CACHE_VERSION}:{user}:{dashboard_id}:{effective_company or ''}:"
		f"{limit}:{from_date or ''}:{to_date or ''}:{board_period or ''}:{filters_key}:"
		f"{request_suffix}:{profile_modified}"
	)
	if use_cache and not refresh:
		cached = frappe.cache().get_value(cache_key)
		if cached:
			return cached

	reset_batch_kpi_cache()
	_warm_board_kpi_cache(
		user,
		effective_company,
		resolved_widgets,
		board_period=board_period,
		batch_compare=batch_compare,
		filters=board_filters,
		filters_key=filters_key,
		from_date=from_date,
		to_date=to_date,
	)

	widgets_out: dict[str, Any] = {}
	errors: dict[str, str] = {}
	for widget in resolved_widgets:
		key = widget["key"]
		try:
			widget_for_build = _apply_period_to_widget(widget, board_period)
			payload = _build_widget_payload(
				user,
				effective_company,
				widget_for_build,
				from_date=from_date,
				to_date=to_date,
				limit=limit,
				filters=board_filters,
				compare_override=batch_compare,
			)
			payload = dict(payload)
			alias_keys = payload.pop("_alias_keys", None) or []
			_register_widget_payload_aliases(widgets_out, widget_for_build, payload)
			for alias in alias_keys:
				alias_key = str(alias).strip()
				if alias_key:
					widgets_out[alias_key] = payload
			if key == "receivables_card" and not _single_territory_filter(parsed_filters):
				_register_receivables_territory_aliases(widgets_out, payload)
		except Exception as exc:
			errors[key] = str(exc)
			frappe.log_error(title=f"dashboard_board.{key}", message=frappe.get_traceback())

	result = {
		"dashboard_id": dashboard_id,
		"requested_dashboard_id": requested_dashboard_id,
		"widgets": widgets_out,
		"errors": errors or None,
		"meta": {
			"schema_version": 1,
			"board_data_revision": BOARD_DATA_REVISION,
			"widget_count": len(widgets_out),
			"cached_at": datetime.utcnow().isoformat() + "Z",
			"company": effective_company,
			"profile": profile_name,
			"resolved_from": requested_dashboard_id if requested_dashboard_id != dashboard_id else None,
		},
	}

	if use_cache:
		frappe.cache().set_value(cache_key, result, expires_in_sec=BOARD_DATA_CACHE_TTL)

	return result


def _build_widget_payload(
	user: str,
	company: Optional[str],
	widget: dict[str, Any],
	*,
	from_date: Optional[str] = None,
	to_date: Optional[str] = None,
	limit: int = 10,
	dimension_override: Optional[str] = None,
	filters: Any = None,
	drill_depth: Optional[int] = None,
	compare_override: Optional[str] = None,
	extra: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
	widget_type = widget["widget_type"]
	effective_view = _resolve_effective_view(
		widget,
		drill_depth=drill_depth,
		dimension_override=dimension_override,
	)

	if widget.get("key") == "receivables_card":
		return _receivables_card_widget_payload(user, company, widget, limit, filters=filters)

	if widget_type in NAV_WIDGET_TYPES:
		return _link_widget_payload(widget)
	if widget_type == "KPI":
		return _kpi_widget_payload(
			user,
			company,
			widget,
			from_date,
			to_date,
			filters=filters,
			compare_override=compare_override,
		)
	if widget_type in TABLE_WIDGET_TYPES or effective_view == "table":
		return _table_widget_payload(
			user,
			company,
			widget,
			from_date,
			to_date,
			limit,
			dimension_override=dimension_override,
			filters=filters,
			drill_depth=drill_depth,
			compare_override=compare_override,
			extra=extra,
		)
	if widget_type in CHART_WIDGET_TYPES or effective_view in ("pie", "donut", "bar", "line"):
		return _chart_widget_payload(
			user,
			company,
			widget,
			from_date,
			to_date,
			limit,
			dimension_override=dimension_override,
			filters=filters,
			drill_depth=drill_depth,
			compare_override=compare_override,
			render_hint=effective_view if effective_view in ("pie", "donut", "bar", "line") else None,
		)
	if widget_type == "MATRIX":
		frappe.throw(
			_("MATRIX widgets require secondary_dimension (not supported in v1 widget data API yet)"),
			frappe.ValidationError,
		)

	config = widget.get("config") or {}
	if _widget_data_source(config) == "attention":
		return _attention_widget_payload(
			user,
			company,
			widget,
			limit,
			compare_override=compare_override,
		)

	return _legacy_widget_payload(user, company, widget, from_date, to_date, limit, extra or {})


def _widget_data_source(config: dict[str, Any]) -> Optional[str]:
	raw = config.get("payload_source") or config.get("data_source")
	if not raw:
		return None
	return str(raw).strip().lower() or None


def _trend_widget_payload(
	user: str,
	company: Optional[str],
	widget: dict[str, Any],
	from_date: Optional[str],
	to_date: Optional[str],
	*,
	filters: Any = None,
	compare_override: Optional[str] = None,
) -> dict[str, Any]:
	config = widget.get("config") or {}
	metric = (widget.get("metric_key") or config.get("metric") or "net_sales").strip().lower()
	group_by = (config.get("group_by") or "month").strip().lower()
	period = _period_from_widget(widget, config)
	compare_mode = _compare_from_widget(widget, config, compare_override)

	from erp_analysis.services.sales_trends import get_sales_trends

	trends = get_sales_trends(
		user=user,
		company=company,
		from_date=from_date,
		to_date=to_date,
		group_by=group_by,
		metric=metric,
		filters=filters,
		compare=compare_mode,
		period=period,
	)

	series = []
	for row in trends.get("series") or []:
		point = {
			"label": row.get("label") or row.get("period"),
			"value": row.get("value"),
			"period": row.get("period"),
		}
		if compare_mode:
			_apply_compare_point(point, row, compare_mode)
		series.append(point)

	show_currency = widget.get("show_currency_symbol")
	if show_currency is None:
		show_currency = _is_currency_metric(metric)

	widget_type = widget["widget_type"]
	hint = widget_type.lower() if widget_type in CHART_WIDGET_TYPES else "line"
	comparison = trends.get("comparison") or {}
	show_ly = bool(compare_mode or widget.get("show_ly") or config.get("compare") == "ly")

	payload: dict[str, Any] = {
		"widget_key": widget["key"],
		"widget_type": widget_type,
		"label": widget.get("label"),
		"chart": {
			"series": series,
			"metric": metric,
			"group_by": group_by,
			"filters": (trends.get("meta") or {}).get("filters") or {},
			"compare": compare_mode,
			"compare_label": _compare_column_label(compare_mode),
			"show_currency_symbol": bool(show_currency),
			"comparison": comparison,
		},
		"meta": {
			"schema_version": 1,
			**(trends.get("meta") or {}),
			"render_hint": hint,
			"data_source": "trend",
		},
	}
	if comparison:
		payload["chart"]["summary"] = {
			"value": comparison.get("value"),
			"value_ly": comparison.get("value_ly"),
			"change_pct": comparison.get("change_pct"),
		}
	if show_ly:
		payload["show_ly"] = True
	return payload


def _customer_widget_payload(
	user: str,
	company: Optional[str],
	widget: dict[str, Any],
	from_date: Optional[str],
	to_date: Optional[str],
	limit: int,
	*,
	filters: Any = None,
	compare_override: Optional[str] = None,
) -> dict[str, Any]:
	config = widget.get("config") or {}
	section = (config.get("section") or "top").strip().lower()
	period = _period_from_widget(widget, config)
	compare_mode = _compare_from_widget(widget, config, compare_override)

	from erp_analysis.services.sales_customers import get_sales_customer_analysis

	analysis = get_sales_customer_analysis(
		user=user,
		company=company,
		section=section,
		from_date=from_date,
		to_date=to_date,
		period=period,
		filters=filters,
		limit=limit,
		compare=compare_mode,
		inactive_days=int(config.get("inactive_days") or 90),
		decline_threshold_pct=float(config.get("decline_threshold_pct") or 10),
		concentration_top_n=int(config.get("concentration_top_n") or 10),
	)

	rows = []
	for row in analysis.get("data") or []:
		if section == "concentration":
			rows.append(
				{
					"dimension": row.get("label"),
					"metric": row.get("contribution_pct"),
					"contribution_pct": row.get("contribution_pct"),
					"top_n": row.get("top_n"),
				}
			)
		else:
			rows.append(
				{
					"dimension": row.get("customer_name") or row.get("customer"),
					"dimension_value": row.get("customer"),
					"metric": row.get("net_sales") or row.get("sales"),
					"metric_ly": row.get("comparison_sales"),
					"change_pct": row.get("growth_pct") or row.get("variance_pct"),
					"gross_profit": row.get("gross_profit"),
					"gp_pct": row.get("gp_pct"),
					"contribution_pct": row.get("contribution_pct"),
					"invoice_count": row.get("invoice_count"),
					"rank": row.get("rank"),
					"decline_pct": row.get("decline_pct"),
					"days_inactive": row.get("days_inactive"),
					"last_invoice_date": row.get("last_invoice_date"),
					"first_invoice_date": row.get("first_invoice_date"),
				}
			)

	columns = _parse_table_columns(widget, compare=compare_mode or False)
	if section == "concentration":
		columns = config.get("table_columns") or [
			{"key": "dimension", "label": "Segment", "flex": 1.4, "align": "left"},
			{"key": "metric", "label": "Contribution %", "format": "percent", "flex": 1, "align": "right"},
		]

	return {
		"widget_key": widget["key"],
		"widget_type": widget["widget_type"],
		"label": widget.get("label"),
		"table": {
			"columns": columns,
			"rows": rows,
			"section": section,
			"filters": (analysis.get("meta") or {}).get("filters") or {},
			"compare": compare_mode,
			"show_currency_symbol": False,
		},
		"meta": {
			"schema_version": 1,
			**(analysis.get("meta") or {}),
			"render_hint": "ranking" if widget["widget_type"] == "RANKING" else "table",
			"data_source": "customer",
		},
	}


def _format_currency_compact(value: Any) -> str:
	num = float(value or 0)
	if abs(num) >= 1_000_000:
		return f"{num / 1_000_000:.2f}M"
	if abs(num) >= 1_000:
		return f"{num / 1_000:.2f}K"
	return f"{num:.2f}"


def _attention_widget_payload(
	user: str,
	company: Optional[str],
	widget: dict[str, Any],
	limit: int,
	*,
	compare_override: Optional[str] = None,
) -> dict[str, Any]:
	config = widget.get("config") or {}
	section = (config.get("section") or "all").strip().lower()
	period = _period_from_widget(widget, config)

	from erp_analysis.services.sales_attention import get_sales_attention

	attention = get_sales_attention(
		user=user,
		company=company,
		section=section,
		limit=limit,
		period=period,
		decline_threshold_pct=float(config.get("decline_threshold_pct") or 25),
		stale_so_days=int(config.get("stale_so_days") or 90),
	)

	rows = []
	for alert in attention.get("data") or []:
		rows.append(
			{
				"dimension": alert.get("title"),
				"dimension_value": alert.get("entity_name"),
				"metric": alert.get("value"),
				"severity": alert.get("severity"),
				"alert_type": alert.get("type"),
				"description": alert.get("description"),
				"entity_type": alert.get("entity_type"),
				"change_pct": alert.get("change_pct"),
				"reference_doctype": alert.get("reference_doctype"),
				"reference_name": alert.get("reference_name"),
				"drilldown": alert.get("drilldown"),
			}
		)

	columns = config.get("table_columns") or [
		{"key": "dimension", "label": "Alert", "flex": 1.6, "align": "left"},
		{"key": "description", "label": "Detail", "flex": 1.4, "align": "left"},
		{"key": "metric", "label": "Value", "format": "currency_compact", "flex": 1, "align": "right"},
	]

	value_format = (config.get("format") or "currency_compact").strip().lower()
	list_rows: list[dict[str, Any]] = []
	for row in rows:
		label = row.get("dimension") or row.get("dimension_value")
		value = row.get("metric")
		list_rows.append(
			{
				"label": label,
				"value": value,
				"format": value_format,
				"value_display": _format_currency_compact(value),
				"dimension": label,
				"metric": value,
				"meta": {
					"severity": row.get("severity"),
					"alert_type": row.get("alert_type"),
					"change_pct": row.get("change_pct"),
				},
			}
		)

	is_list = widget["widget_type"] == "LIST"
	render_hint = "cards" if is_list else ("ranking" if widget["widget_type"] == "RANKING" else "table")

	payload: dict[str, Any] = {
		"widget_key": widget["key"],
		"widget_type": widget["widget_type"],
		"label": widget.get("label"),
		"table": {
			"columns": columns,
			"rows": rows,
			"section": section,
			"compare": None,
			"show_currency_symbol": False,
			"currency_display": {"show_symbol": False},
		},
		"rows": list_rows,
		"data": {
			"rows": list_rows,
			"items": list_rows,
		},
		"meta": {
			"schema_version": 1,
			**(attention.get("meta") or {}),
			"render_hint": render_hint,
			"data_source": "attention",
			"format": value_format,
			"value_format": value_format,
		},
	}
	if config.get("section_title"):
		payload["section_title"] = config.get("section_title")
		payload["meta"]["section_title"] = config.get("section_title")
	return payload


def _resolve_kpi_module_key(widget: dict[str, Any], metric: str) -> str:
	from erp_analysis.services.module_kpis import COLLECTION_KPI_METRICS

	module_key = (widget.get("module_key") or "sales").strip().lower()
	metric = (metric or "").strip().lower()
	widget_key = (widget.get("key") or "").strip().lower()
	if widget_key == "home_total_purchases_kpi" or metric in ("total_purchases", "purchases_ytd", "open_po_value"):
		return "purchase"
	if widget_key == "home_total_payables_kpi" or metric in ("total_payable", "total_payables"):
		return "payables"
	if metric in COLLECTION_KPI_METRICS:
		return "collection"
	from erp_analysis.services.module_kpis import SALES_ORDERS_KPI_METRICS

	if widget_key in ("sales_orders_kpi", "total_orders_kpi", "total_orders") or metric in SALES_ORDERS_KPI_METRICS:
		return "sales_orders"
	return module_key


def _is_health_gauge_widget(widget: dict[str, Any], config: dict[str, Any], metric: str) -> bool:
	if (metric or "").strip().lower() == "health_score":
		return True
	render_hint = (config.get("render_hint") or "").strip().lower()
	return render_hint == "gauge"


# Explicit payload field names for mobile KPI mapping (in addition to generic `value`).
KPI_METRIC_PAYLOAD_FIELDS: dict[str, list[str]] = {
	"inventory_value": ["inventory_value", "total_inventory_value"],
	"value": ["inventory_value", "total_inventory_value"],
	"stock_value": ["inventory_value", "total_inventory_value"],
	"stock_qty": ["stock_qty", "total_qty", "totalQty"],
	"total_qty": ["stock_qty", "total_qty", "totalQty"],
	"available_value": ["available_value", "availableValue"],
	"reserved_value": ["reserved_value", "reservedValue"],
	"turnover": ["turnover", "inventory_turnover", "inventory_turnover_ratio", "inventoryTurnoverRatio"],
	"inventory_turnover": ["turnover", "inventory_turnover", "inventory_turnover_ratio", "inventoryTurnoverRatio"],
	"days_of_inventory": ["days_of_inventory", "days_of_cover", "avg_cover_days", "averageDaysInInventory"],
	"avg_days": ["days_of_inventory", "days_of_cover", "avg_cover_days", "averageDaysInInventory"],
	"days_of_cover": ["days_of_inventory", "days_of_cover", "avg_cover_days", "averageDaysInInventory"],
	"net_sales": ["net_sales", "total_sales", "sales_ytd"],
	"cogs": ["cogs", "cost_of_goods_sold", "cost_of_goods_sold_value"],
	"cost_of_goods_sold": ["cogs", "cost_of_goods_sold", "cost_of_goods_sold_value"],
	"gross_profit": ["gross_profit", "gp", "gross_profit_value"],
	"gp_pct": ["gp_pct", "gross_profit_pct", "gp_margin"],
	"gross_profit_pct": ["gp_pct", "gross_profit_pct", "gp_margin"],
}


def _metric_payload_fields(metric: str, value: Any) -> dict[str, Any]:
	names = KPI_METRIC_PAYLOAD_FIELDS.get((metric or "").strip().lower())
	if not names or value is None:
		return {}
	return {name: value for name in names}


def _build_kpi_widget_response(
	widget: dict[str, Any],
	kpi: dict[str, Any],
	*,
	format_hint: str,
	show_currency: bool,
	is_gauge: bool = False,
) -> dict[str, Any]:
	config = widget.get("config") or {}
	metric = (widget.get("metric_key") or "net_sales").strip().lower()
	widget_key = (widget.get("key") or "").strip()
	kpi_id = config.get("kpi_id") or widget_key or metric
	value = kpi.get("value")
	value_ly = kpi.get("value_ly")
	change_pct = kpi.get("change_pct")
	show_ly = bool(widget.get("show_ly") or config.get("compare") == "ly" or value_ly is not None)

	kpi_entry: dict[str, Any] = {
		"kpi_id": kpi_id,
		"value": value,
		"format": format_hint,
	}
	if value_ly is not None:
		kpi_entry["previous"] = value_ly
		kpi_entry["value_ly"] = value_ly
	if change_pct is not None:
		kpi_entry["change_pct"] = change_pct
	if kpi.get("label") or widget.get("label"):
		kpi_entry["label"] = kpi.get("label") or widget.get("label")

	metric_fields = _metric_payload_fields(metric, value)
	if metric_fields:
		kpi_entry.update(metric_fields)

	result: dict[str, Any] = {
		"widget_key": widget_key,
		"widget_type": "KPI",
		"label": widget.get("label"),
		"kpis": [kpi_entry],
		"kpi": {
			"kpi_id": kpi_id,
			"value": value,
			"value_ly": value_ly,
			"change_pct": change_pct,
			"direction": kpi.get("direction"),
			"metric": metric,
			"label": kpi.get("label") or widget.get("label"),
			"format": format_hint,
			"show_currency_symbol": bool(show_currency),
			"subtitle": config.get("subtitle"),
			**metric_fields,
		},
		"value": value,
		**metric_fields,
		"data": {
			"value": value,
			"format": format_hint,
			"kpi_id": kpi_id,
			**metric_fields,
		},
		"meta": {
			"schema_version": 1,
			**(kpi.get("meta") or {}),
			"render_hint": "gauge" if is_gauge else "kpi",
			"kpi_id": kpi_id,
			"format": format_hint,
			"section_title": config.get("section_title"),
			"row_group": config.get("row_group"),
		},
	}
	if config.get("section_title"):
		result["section_title"] = config.get("section_title")
	if config.get("row_group"):
		result["row_group"] = config.get("row_group")
	action = config.get("action")
	if isinstance(action, dict) and action.get("type"):
		result["action"] = action
		result["meta"]["action"] = action
	if show_ly:
		result["show_ly"] = True
	if is_gauge:
		result["config"] = {"max_value": config.get("max_value") or 100}
	else:
		kpi_config: dict[str, Any] = {}
		for key in (
			"format",
			"date_scope",
			"drill_widget_key",
			"drill_path",
			"drill_views",
		):
			if config.get(key) is not None:
				kpi_config[key] = config.get(key)
		if kpi_config:
			result["config"] = kpi_config
	return result


def _kpi_widget_payload(
	user: str,
	company: Optional[str],
	widget: dict[str, Any],
	from_date: Optional[str],
	to_date: Optional[str],
	*,
	filters: Any = None,
	compare_override: Optional[str] = None,
) -> dict[str, Any]:
	config = widget.get("config") or {}
	metric = (widget.get("metric_key") or "net_sales").strip().lower()
	module_key = _resolve_kpi_module_key(widget, metric)
	period = _period_from_widget(widget, config)
	compare = _compare_from_widget(widget, config, compare_override)
	filters_key = _filters_cache_key(filters)
	is_gauge = _is_health_gauge_widget(widget, config, metric)
	use_dashboard_kpi = _uses_dashboard_sales_kpi(
		widget, config, user=user, company=company, filters=filters
	)
	cache_metric = f"{module_key}:{metric}" if module_key != "sales" else metric
	if use_dashboard_kpi:
		cache_metric = f"dashboard:{metric}"
	if is_gauge:
		cache_metric = f"health:{module_key}:{widget.get('key')}"

	kpi = get_cached_kpi(company, cache_metric, period, compare, filters_key)
	if kpi is None:
		from erp_analysis.services.kpi.home_metrics import get_home_kpi, is_home_kpi
		from erp_analysis.services.module_kpis import get_module_kpi, is_module_kpi

		if use_dashboard_kpi:
			from erp_analysis.services.analytics_sales import get_dashboard_sales_kpi

			kpi = get_dashboard_sales_kpi(
				user=user,
				company=company,
				metric=metric,
				from_date=from_date,
				to_date=to_date,
				period=period,
				filters=filters,
				compare=compare,
			)
		elif _uses_filter_aware_sales_kpi(widget, metric, filters):
			from erp_analysis.services.analytics_sales import get_sales_kpi

			kpi = get_sales_kpi(
				user=user,
				company=company,
				metric=metric,
				from_date=from_date,
				to_date=to_date,
				period=period,
				filters=filters,
				compare=compare,
			)
		elif is_gauge or is_home_kpi(metric):
			kpi = get_home_kpi(
				user=user,
				company=company,
				metric_key=metric,
				module_key=module_key,
				widget_key=widget.get("key") or "",
				period=period,
				compare=compare,
				from_date=from_date,
				to_date=to_date,
			)
		elif is_module_kpi(module_key, metric):
			kpi = get_module_kpi(
				user=user,
				company=company,
				module_key=module_key,
				metric_key=metric,
				period=period,
				filters=filters,
			)
		else:
			from erp_analysis.services.analytics_sales import get_sales_kpi

			kpi = get_sales_kpi(
				user=user,
				company=company,
				metric=metric,
				from_date=from_date,
				to_date=to_date,
				period=period,
				filters=filters,
				compare=compare,
			)
		set_cached_kpi(company, cache_metric, period, compare, filters_key, kpi)

	widget_key = (widget.get("key") or "").strip()
	if widget_key in ("sales_orders_kpi", "total_orders_kpi", "total_orders"):
		from erp_analysis.services.sales_open_orders_widget import enrich_open_so_kpi_meta

		kpi = enrich_open_so_kpi_meta(kpi, user=user, company=company, filters=filters)

	format_hint = config.get("format") or kpi.get("meta", {}).get("format") or _default_format_for_metric(metric)
	if is_gauge:
		format_hint = "score"
	show_currency = widget.get("show_currency_symbol")
	if show_currency is None:
		show_currency = _is_currency_metric(metric) and not is_gauge

	return _build_kpi_widget_response(
		widget,
		kpi,
		format_hint=format_hint,
		show_currency=bool(show_currency),
		is_gauge=is_gauge,
	)


def _empty_drill_scope_payload(
	widget: dict[str, Any],
	dimension_override: Optional[str],
	drill_depth: Optional[int],
) -> dict[str, Any]:
	config = widget.get("config") or {}
	drill_path = _normalize_drill_path(config.get("drill_path"))
	msg = _(
		"Drill-down is missing a parent filter (for example division). "
		"Pass filters={\"division\":[\"Retail\"]} with drill_depth."
	)
	result: dict[str, Any] = {
		"widget_key": widget["key"],
		"widget_type": widget["widget_type"],
		"label": widget.get("label"),
		"table": {
			"columns": _parse_table_columns(widget, compare=config.get("compare")),
			"rows": [],
			"metric": widget.get("metric_key") or "net_sales",
			"dimension": dimension_override or widget.get("dimension_key"),
			"filters": {},
			"compare": config.get("compare"),
			"show_currency_symbol": bool(widget.get("show_currency_symbol")),
			"row_limit": config.get("row_limit"),
		},
		"rows": [],
		"meta": {
			"schema_version": 1,
			"empty_state": "missing_drill_filter",
			"empty_message": msg,
			"drill_path": drill_path or None,
			"drill_depth": drill_depth,
			"missing_drill_filters": ["division"],
		},
	}
	return result


def _table_widget_payload(
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
	extra: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
	config = widget.get("config") or {}
	limit = _effective_widget_row_limit(widget, limit)
	if extra is not None and extra.get("_drill_scope_ok") is False:
		return _empty_drill_scope_payload(widget, dimension_override, drill_depth)
	if _widget_data_source(config) == "attention":
		return _attention_widget_payload(
			user,
			company,
			widget,
			limit,
			compare_override=compare_override,
		)
	if _widget_data_source(config) == "customer":
		return _customer_widget_payload(
			user,
			company,
			widget,
			from_date,
			to_date,
			limit,
			filters=filters,
			compare_override=compare_override,
		)
	if _widget_data_source(config) == "legacy_table":
		return _legacy_table_widget_payload(user, company, widget, limit)
	if _widget_data_source(config) == "legacy_chart" and widget["widget_type"] == "RANKING":
		return _legacy_ranking_from_chart_payload(user, company, widget, limit, filters=filters)
	if _widget_data_source(config) == "open_sales_orders" or widget.get("key") == "sales_open_orders_list":
		from erp_analysis.services.sales_open_orders_widget import build_open_sales_orders_widget_payload

		return build_open_sales_orders_widget_payload(
			user,
			company,
			widget,
			limit=limit,
			filters=filters,
			drill_depth=drill_depth,
		)

	metric = widget.get("metric_key") or "net_sales"
	dimension, config, resolved_depth = resolve_chart_dimension(
		widget,
		dimension_override=dimension_override,
		drill_depth=drill_depth,
	)
	drill_path = _normalize_drill_path(config.get("drill_path"))
	next_dim = next_drill_dimension(dimension, config)
	compare_mode = _compare_from_widget(widget, config, compare_override)
	period = _period_from_widget(widget, config)
	use_extended = bool(config.get("extended_metrics"))

	if use_extended:
		from erp_analysis.services.analytics_sales import get_sales_performance

		analysis = get_sales_performance(
			user=user,
			company=company,
			from_date=from_date,
			to_date=to_date,
			dimension=dimension,
			filters=filters,
			limit=limit,
			compare=compare_mode,
			period=period,
		)
	else:
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
			period=period,
		)

	rows = []
	for row in analysis.get("data") or []:
		if use_extended:
			rows.append(
				{
					"dimension": row.get("label") or row.get("dimension_value"),
					"dimension_value": row.get("dimension_value"),
					"metric": row.get("net_sales") or row.get("metric_value"),
					"metric_ly": row.get("comparison_sales"),
					"change_pct": row.get("variance_pct"),
					"gross_profit": row.get("gross_profit"),
					"gp_pct": row.get("gp_pct"),
					"contribution_pct": row.get("contribution_pct"),
					"invoice_count": row.get("invoice_count"),
					"quantity": row.get("quantity"),
					"rank": row.get("rank"),
				}
			)
		else:
			entry = {
				"dimension": row.get("label") or row.get("dimension_value"),
				"dimension_value": row.get("dimension_value"),
				"metric": row.get("metric_value"),
				"metric_ly": row.get("metric_value_ly"),
				"change_pct": row.get("change_pct"),
				"rank": row.get("rank"),
			}
			if row.get("gp_pct") is not None:
				entry["gp_pct"] = row.get("gp_pct")
			if row.get("gross_profit") is not None:
				entry["gross_profit"] = row.get("gross_profit")
			rows.append(entry)

	dim_key = (dimension or "").strip().lower()
	if dim_key in ("sub_group", "item_group", "group"):
		for entry in rows:
			full = str(entry.get("dimension_value") or entry.get("dimension") or "").strip()
			if not full:
				continue
			entry["dimension"] = full
			entry["label"] = full
			entry["name"] = full
			entry["title"] = full
			entry["sub_group"] = full
			entry["item_group"] = full
			entry["drill_filter"] = {"sub_group": [full]}

	sub_group_label_meta: dict[str, Any] = {}
	if dim_key in ("sub_group", "item_group", "group"):
		sub_group_label_meta = {
			"sub_group_label_display": "full",
			"strip_division_prefix_from_sub_group": False,
			"drill_row_label_field": "dimension_value",
		}

	columns = _parse_table_columns(widget, compare=compare_mode or False)
	applied_filters = (analysis.get("meta") or {}).get("filters") or {}
	from erp_analysis.services.analytics_sales import _coalesce_dashboard_filter_keys

	if isinstance(applied_filters, dict):
		applied_filters = _coalesce_dashboard_filter_keys(dict(applied_filters))
	show_currency = widget.get("show_currency_symbol")
	if show_currency is None:
		show_currency = _is_currency_metric(metric)

	result: dict[str, Any] = {
		"widget_key": widget["key"],
		"widget_type": widget["widget_type"],
		"label": widget.get("label"),
		"table": {
			"columns": columns,
			"rows": rows,
			"metric": metric,
			"dimension": dimension,
			"filters": applied_filters,
			"compare": compare_mode,
			"show_currency_symbol": bool(show_currency),
			"extended_metrics": use_extended,
			"row_limit": limit,
		},
		"meta": {
			"schema_version": 1,
			**(analysis.get("meta") or {}),
			"render_hint": "ranking" if widget["widget_type"] == "RANKING" else "table",
			"drill_path": drill_path or None,
			"drill_depth": resolved_depth,
			"next_dimension": next_dim,
			"drillable": bool(next_dim),
			"row_limit": limit,
			"dimension_label": _dimension_display_label(user, company, dimension),
			**sub_group_label_meta,
		},
	}
	if resolved_depth and int(resolved_depth) > 0:
		result.pop("section_title", None)
		result["meta"].pop("section_title", None)
	elif config.get("section_title"):
		result["section_title"] = config.get("section_title")
		result["meta"]["section_title"] = config.get("section_title")
	if not rows:
		result["meta"]["empty_state"] = "no_rows"
		result["meta"]["empty_message"] = _("No sales data for the selected filters.")
	if (dimension or "").strip().lower() == "brand" and isinstance(applied_filters, dict) and rows:
		from erp_analysis.services.sales_drill import assess_brand_drill_scope
		from frappe.utils import getdate

		analysis_meta = analysis.get("meta") or {}
		scope = assess_brand_drill_scope(
			company=company,
			from_date=getdate(analysis_meta.get("from_date") or from_date or frappe.utils.nowdate()),
			to_date=getdate(analysis_meta.get("to_date") or to_date or frappe.utils.nowdate()),
			filters=applied_filters,
			rows=rows,
		)
		result.update({k: scope[k] for k in ("drill_scope_status", "accept_response", "is_division_wide_brand_mix") if k in scope})
		result["meta"].update(scope)
	_mirror_table_rows_for_mobile_chart(
		result,
		rows,
		metric=metric,
		dimension=dimension,
		applied_filters=applied_filters,
		compare_mode=compare_mode,
		show_currency=bool(show_currency),
	)
	# Mobile drill parsers often read payload.rows before table.rows
	result["rows"] = rows
	return result


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
	render_hint: Optional[str] = None,
) -> dict[str, Any]:
	config = widget.get("config") or {}
	if _widget_data_source(config) == "trend":
		payload = _trend_widget_payload(
			user,
			company,
			widget,
			from_date,
			to_date,
			filters=filters,
			compare_override=compare_override,
		)
		if render_hint:
			payload["meta"]["render_hint"] = render_hint
		return payload
	if _widget_data_source(config) == "legacy_chart":
		payload = _legacy_chart_widget_payload(
			user,
			company,
			widget,
			limit,
			render_hint=render_hint,
		)
		if render_hint:
			payload["meta"]["render_hint"] = render_hint
		return payload
	if _widget_data_source(config) == "legacy_table" and config.get("legacy_method"):
		payload = _legacy_chart_from_table_payload(
			user,
			company,
			widget,
			limit,
			render_hint=render_hint,
		)
		if render_hint:
			payload["meta"]["render_hint"] = render_hint
		return payload
	if _widget_data_source(config) == "legacy" and config.get("legacy_method"):
		payload = _call_legacy_method(
			config.get("legacy_method"),
			company=company,
			limit=limit,
			extra=config.get("legacy_params"),
		)
		section_meta = _legacy_widget_section_meta(config)
		return {
			"widget_key": widget["key"],
			"widget_type": widget["widget_type"],
			"label": widget.get("label"),
			"data": payload,
			"meta": {
				"schema_version": 1,
				"legacy_method": config.get("legacy_method"),
				"render_hint": "list",
				**section_meta,
			},
		}

	metric = widget.get("metric_key") or "net_sales"
	dimension, config, resolved_depth = resolve_chart_dimension(
		widget,
		dimension_override=dimension_override,
		drill_depth=drill_depth,
	)
	drill_path = _normalize_drill_path(config.get("drill_path"))
	next_dim = next_drill_dimension(dimension, config)
	compare_mode = _compare_from_widget(widget, config, compare_override)
	period = _period_from_widget(widget, config)

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
		period=period,
	)

	series = []
	for row in analysis.get("data") or []:
		point = {
			"label": row.get("label") or row.get("dimension_value"),
			"value": row.get("metric_value"),
			"dimension_value": row.get("dimension_value"),
		}
		if compare_mode:
			_apply_compare_point(point, row, compare_mode)
		series.append(point)

	applied_filters = (analysis.get("meta") or {}).get("filters") or {}
	show_currency = widget.get("show_currency_symbol")
	if show_currency is None:
		show_currency = _is_currency_metric(metric)
	hint = render_hint or widget["widget_type"].lower()

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
			"compare_label": _compare_column_label(compare_mode),
			"show_currency_symbol": bool(show_currency),
		},
		"meta": {
			"schema_version": 1,
			**(analysis.get("meta") or {}),
			"render_hint": hint,
			"drill_path": drill_path or None,
			"drill_depth": resolved_depth,
			"next_dimension": next_dim,
			"drillable": bool(next_dim),
		},
	}


def _parse_table_columns(widget: dict[str, Any], *, compare: bool | str | None = False) -> list[dict[str, Any]]:
	raw = widget.get("table_columns_json")
	if not raw:
		config = widget.get("config") or {}
		raw = config.get("table_columns")
	if isinstance(raw, str) and raw.strip():
		try:
			parsed = json.loads(raw)
			if isinstance(parsed, list):
				return parsed
		except Exception:
			pass
	if isinstance(raw, list):
		return raw
	return _default_table_columns(compare=compare)


def _default_table_columns(*, compare: bool | str | None = False) -> list[dict[str, Any]]:
	columns = [
		{"key": "dimension", "label": "Name", "flex": 1.4, "align": "left", "min_width": 72},
		{"key": "metric", "label": "Value", "format": "currency_compact", "flex": 1.1, "align": "right", "min_width": 72},
	]
	if compare:
		columns.extend(
			[
				{
					"key": "metric_ly",
					"label": _compare_column_label(compare),
					"format": "currency_compact",
					"flex": 1.2,
					"align": "right",
					"min_width": 80,
				},
				{"key": "change_pct", "label": "Δ%", "format": "percent", "width": 56, "align": "right"},
			]
		)
	return columns


def _compare_column_label(compare_mode: bool | str | None) -> str:
	if compare_mode in ("previous_period", "prev"):
		return "Prev"
	if compare_mode in ("ly", "previous_year"):
		return "LY"
	if isinstance(compare_mode, str) and compare_mode:
		return "Compare"
	return "LY"


def _apply_compare_point(point: dict[str, Any], row: dict[str, Any], compare_mode: Optional[str]) -> None:
	if not compare_mode:
		return
	point["value_ly"] = row.get("value_ly") or row.get("metric_value_ly") or row.get("comparison_sales")
	point["change_pct"] = row.get("change_pct") or row.get("variance_pct")


def _default_format_for_metric(metric: str) -> str:
	if metric in (
		"transactions",
		"sales_qty",
		"customer_count",
		"active_customers",
		"stock_qty",
		"total_qty",
		"days_of_inventory",
		"avg_days",
		"days_of_cover",
		"low_stock",
		"low_stock_count",
		"non_moving",
		"non_moving_count",
	):
		return "integer"
	if metric in ("gp_pct", "discount_pct"):
		return "percent"
	if metric in ("turnover", "inventory_turnover"):
		return "decimal"
	if metric in (
		"net_sales",
		"gross_sales",
		"average_transaction",
		"gross_profit",
		"discount_amount",
		"sales_return",
		"inventory_value",
		"value",
		"stock_value",
		"available_value",
		"reserved_value",
	):
		return "currency_compact"
	return "number"


def _is_currency_metric(metric: str) -> bool:
	return metric in (
		"net_sales",
		"gross_sales",
		"average_transaction",
		"gross_profit",
		"discount_amount",
		"sales_return",
		"inventory_value",
		"value",
		"stock_value",
		"available_value",
		"reserved_value",
	)


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


def _call_legacy_method(
	method_path: str,
	*,
	company: Optional[str] = None,
	from_date: Optional[str] = None,
	to_date: Optional[str] = None,
	limit: Optional[int] = None,
	extra: Optional[dict[str, Any]] = None,
) -> Any:
	method = frappe.get_attr(method_path)
	params = inspect.signature(method).parameters
	call_kwargs: dict[str, Any] = {}
	if "company" in params and company:
		call_kwargs["company"] = company
	if "from_date" in params and from_date:
		call_kwargs["from_date"] = from_date
	if "to_date" in params and to_date:
		call_kwargs["to_date"] = to_date
	if "limit" in params and limit:
		call_kwargs["limit"] = limit
	if "fast" in params:
		call_kwargs["fast"] = bool((extra or {}).get("fast", True))
	for optional_key in ("months", "warehouse", "territory", "old_days"):
		if optional_key in params and optional_key in (extra or {}):
			call_kwargs[optional_key] = extra[optional_key]
	return method(**call_kwargs)


def _extract_rows(payload: Any, rows_key: str) -> list[Any]:
	data = payload
	for part in (rows_key or "rows").split("."):
		if not isinstance(data, dict):
			return []
		data = data.get(part)
	if isinstance(data, list):
		return data
	if isinstance(data, dict):
		return data
	return []


def _legacy_series_from_payload(payload: Any, config: dict[str, Any]) -> list[dict[str, Any]]:
	if isinstance(payload, dict) and isinstance(payload.get("series"), list):
		out: list[dict[str, Any]] = []
		for point in payload["series"]:
			if not isinstance(point, dict):
				continue
			label = point.get("label")
			if label is None:
				continue
			row = {
				"label": str(label),
				"value": round(float(point.get("value") or 0), 2),
			}
			if point.get("dimension_value") is not None:
				row["dimension_value"] = point.get("dimension_value")
			out.append(row)
		return out

	rows_key = config.get("rows_key") or "rows"
	mode = (config.get("rows_mode") or "list").strip().lower()
	label_field = config.get("label_field") or "label"
	value_field = config.get("value_field") or "value"
	label_map = config.get("label_map") or {}

	raw = payload
	if rows_key:
		for part in rows_key.split("."):
			if not isinstance(raw, dict):
				raw = None
				break
			raw = raw.get(part)

	if mode == "dict_to_series" and isinstance(raw, dict):
		series: list[dict[str, Any]] = []
		key_order = list(label_map.keys()) if label_map else list(raw.keys())
		for key in key_order:
			if key not in raw:
				continue
			val = raw[key]
			amount = float(val.get(value_field) if isinstance(val, dict) else val or 0)
			if amount <= 0:
				continue
			series.append(
				{
					"label": label_map.get(key, str(key).replace("_", " ").title()),
					"value": round(amount, 2),
				}
			)
		return series

	rows = raw if isinstance(raw, list) else _extract_rows(payload, rows_key)
	value_fields = config.get("value_fields")
	min_value = float(config.get("min_value") or 0)
	out: list[dict[str, Any]] = []
	for row in rows:
		if not isinstance(row, dict):
			continue
		label = row.get(label_field) or row.get("category") or row.get("territory") or row.get("period")
		if label is None:
			continue
		if isinstance(value_fields, list) and value_fields:
			value = sum(float(row.get(field) or 0) for field in value_fields)
		else:
			value = row.get(value_field) or row.get("value") or row.get("outstanding") or row.get("amount")
		amount = round(float(value or 0), 2)
		if amount < min_value:
			continue
		out.append({"label": str(label), "value": amount})

	sort_by = (config.get("sort_by") or "").strip().lower()
	if sort_by in ("value_desc", "desc", "value"):
		out.sort(key=lambda p: float(p.get("value") or 0), reverse=True)
	elif sort_by in ("value_asc", "asc"):
		out.sort(key=lambda p: float(p.get("value") or 0))

	row_limit = config.get("row_limit")
	if row_limit is not None:
		out = out[: int(row_limit)]

	return out


def _legacy_series_compat(series: list[dict[str, Any]]) -> list[dict[str, Any]]:
	"""Mirror analytics chart points (dimension_value) for older mobile renderers."""
	out: list[dict[str, Any]] = []
	for point in series:
		if not isinstance(point, dict):
			continue
		label = point.get("label")
		row = dict(point)
		if label is not None and row.get("dimension_value") is None:
			row["dimension_value"] = label
		out.append(row)
	return out


def _dedupe_series_by_label(series: list[dict[str, Any]]) -> list[dict[str, Any]]:
	seen: set[str] = set()
	out: list[dict[str, Any]] = []
	for point in series:
		if not isinstance(point, dict):
			continue
		label = str(point.get("label") or point.get("dimension_value") or "").strip()
		if not label:
			continue
		key = label.lower()
		if key in seen:
			continue
		seen.add(key)
		out.append(point)
	return out


def _receivables_card_widget_payload(
	user: str,
	company: Optional[str],
	widget: dict[str, Any],
	limit: int,
	*,
	filters: Any = None,
) -> dict[str, Any]:
	"""Territory breakdown cards for legacy/v2 receivables_card (series + kpis[])."""
	config = dict(widget.get("config") or {})
	legacy_extra = _legacy_extra_from_filters(filters)
	if legacy_extra:
		legacy_params = dict(config.get("legacy_params") or {})
		legacy_params.update(legacy_extra)
		config["legacy_params"] = legacy_params
	config.setdefault("payload_source", "legacy_chart")
	config.setdefault("legacy_method", widget.get("legacy_method") or "erp_analysis.receivables.get_receivables_dashboard")
	config.setdefault("rows_key", "territory_totals")
	config.setdefault("label_field", "territory")
	config.setdefault("value_field", "outstanding")
	config.setdefault("section_title", "Receivables Card")
	config.setdefault("row_group", "receivables_card")

	chart_widget = {
		**widget,
		"widget_type": "PIE",
		"config": config,
	}
	result = _legacy_chart_widget_payload(user, company, chart_widget, limit, render_hint="pie")
	series = _dedupe_series_by_label(_legacy_series_compat(result.get("series") or []))
	row_group = str(config.get("row_group") or "receivables_card")

	kpis: list[dict[str, Any]] = []
	for point in series:
		label = str(point.get("label") or point.get("dimension_value") or "").strip()
		if not label:
			continue
		value = round(float(point.get("value") or 0), 2)
		kpis.append(
			{
				"kpi_id": label,
				"label": label,
				"value": value,
				"format": "currency_compact",
				"row_group": row_group,
			}
		)

	result["widget_type"] = widget.get("widget_type") or "PIE"
	result["series"] = series
	result["kpis"] = kpis
	result["chart"]["series"] = series
	result["data"]["series"] = series
	result["meta"]["row_group"] = row_group
	result["meta"]["section_title"] = config.get("section_title")
	result["meta"]["render_hint"] = "pie"
	if config.get("section_title"):
		result["section_title"] = config.get("section_title")
	if row_group:
		result["row_group"] = row_group

	return result


def _dimension_display_label(user: str, company: Optional[str], dimension_key: str) -> str:
	from erp_analysis.services.analytics_dimensions import resolve_effective_dimension

	try:
		row = resolve_effective_dimension(user, company, dimension_key)
		return str(row.get("label") or dimension_key)
	except Exception:
		return dimension_key.replace("_", " ").title()


def _mirror_table_rows_for_mobile_chart(
	result: dict[str, Any],
	rows: list[dict[str, Any]],
	*,
	metric: str,
	dimension: str,
	applied_filters: dict[str, Any],
	compare_mode: bool | str | None,
	show_currency: bool,
) -> None:
	"""Drill/table payloads: mirror rows into chart.series for clients that only render charts."""
	ranking_series = _legacy_ranking_series_from_table_rows(rows)
	if not ranking_series:
		return
	result["series"] = ranking_series
	result["data"] = {"series": ranking_series, "rows": rows}
	result["chart"] = {
		"series": ranking_series,
		"metric": metric,
		"dimension": dimension,
		"filters": applied_filters,
		"compare": compare_mode,
		"compare_label": _compare_column_label(compare_mode),
		"show_currency_symbol": show_currency,
	}
	meta = result.setdefault("meta", {})
	meta["chart_mirrors_table"] = True


def _legacy_ranking_series_from_table_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
	series: list[dict[str, Any]] = []
	for row in rows:
		if not isinstance(row, dict):
			continue
		label = row.get("dimension_value") or row.get("dimension") or row.get("label")
		value = row.get("metric")
		if label is None:
			continue
		full = str(label)
		entry: dict[str, Any] = {
			"label": full,
			"name": full,
			"value": round(float(value or 0), 2),
			"dimension_value": row.get("dimension_value") or full,
		}
		if row.get("metric_ly") is not None:
			entry["value_ly"] = row.get("metric_ly")
		if row.get("change_pct") is not None:
			entry["change_pct"] = row.get("change_pct")
		if row.get("gp_pct") is not None:
			entry["gp_pct"] = row.get("gp_pct")
		if row.get("gross_profit") is not None:
			entry["gross_profit"] = row.get("gross_profit")
		if row.get("rank") is not None:
			entry["rank"] = row.get("rank")
		series.append(entry)
	return series


def _legacy_widget_section_meta(config: dict[str, Any]) -> dict[str, Any]:
	meta: dict[str, Any] = {}
	section_title = config.get("section_title")
	if section_title:
		meta["section_title"] = section_title
	row_group = config.get("row_group")
	if row_group:
		meta["row_group"] = row_group
	chart_key = config.get("chart_key")
	if chart_key:
		meta["chart_key"] = chart_key
	return meta


def _legacy_ranking_from_chart_payload(
	user: str,
	company: Optional[str],
	widget: dict[str, Any],
	limit: int,
	*,
	filters: Any = None,
) -> dict[str, Any]:
	"""Build RANKING table rows from a legacy chart API series (e.g. overdue customers)."""
	config = dict(widget.get("config") or {})
	legacy_extra = _legacy_extra_from_filters(filters)
	if legacy_extra:
		legacy_params = dict(config.get("legacy_params") or {})
		legacy_params.update(legacy_extra)
		config["legacy_params"] = legacy_params
	widget = {**widget, "config": config}
	chart_payload = _legacy_chart_widget_payload(user, company, widget, limit)
	series = chart_payload.get("series") or []
	rows: list[dict[str, Any]] = []
	for index, point in enumerate(series):
		if not isinstance(point, dict):
			continue
		label = point.get("label") or point.get("dimension_value")
		rows.append(
			{
				"rank": index + 1,
				"dimension": label,
				"dimension_value": point.get("dimension_value") or label,
				"customer": point.get("customer") or point.get("dimension_value") or label,
				"metric": point.get("value"),
				"days": point.get("days") or point.get("days_overdue"),
			}
		)

	columns = config.get("columns") or [
		{"key": "rank", "label": "#", "flex": 0.4, "align": "left"},
		{"key": "dimension", "label": "Customer", "flex": 1.6, "align": "left"},
		{"key": "metric", "label": "Overdue", "format": "currency_compact", "flex": 1, "align": "right"},
		{"key": "days", "label": "Days", "format": "integer", "flex": 0.6, "align": "right"},
	]
	section_meta = _legacy_widget_section_meta(config)
	ranking_series = _legacy_ranking_series_from_table_rows(rows)

	result: dict[str, Any] = {
		"widget_key": widget["key"],
		"widget_type": widget["widget_type"],
		"label": widget.get("label"),
		"table": {
			"columns": columns,
			"rows": rows,
			"show_currency_symbol": True,
		},
		"rows": rows,
		"data": {
			"rows": rows,
			"columns": columns,
		},
		"meta": {
			"schema_version": 1,
			"render_hint": "ranking",
			**section_meta,
			**(chart_payload.get("meta") or {}),
		},
	}
	for meta_key in ("drill_path", "legacy_drill_method"):
		if config.get(meta_key):
			result["meta"][meta_key] = config.get(meta_key)
	if config.get("legacy_drill_method"):
		result["meta"]["drillable"] = True
		result["meta"]["drill_method"] = config.get("legacy_drill_method")
	if ranking_series:
		result["chart"] = {
			"series": ranking_series,
			"metric": widget.get("metric_key") or "value",
			"show_currency_symbol": True,
		}
		result["series"] = ranking_series
		result["data"]["series"] = ranking_series
	return result


def _legacy_chart_from_table_payload(
	user: str,
	company: Optional[str],
	widget: dict[str, Any],
	limit: int,
	*,
	render_hint: Optional[str] = None,
) -> dict[str, Any]:
	"""Build chart series from legacy API rows (e.g. inventory snapshot aging buckets)."""
	config = widget.get("config") or {}
	method_path = config.get("legacy_method") or widget.get("legacy_method")
	if not method_path:
		frappe.throw(
			_("Widget {0} has no legacy_method configured").format(widget["key"]),
			frappe.ValidationError,
		)

	payload = _call_legacy_method(
		method_path,
		company=company,
		limit=limit,
		extra=config.get("legacy_params"),
	)
	series_config = {
		**config,
		"rows_key": config.get("rows_key") or "rows",
		"label_field": config.get("label_field") or "period",
		"value_field": config.get("value_field") or "value",
	}
	series = _legacy_series_compat(_legacy_series_from_payload(payload, series_config))
	metric = widget.get("metric_key") or config.get("metric") or "value"
	dimension = config.get("dimension") or series_config.get("label_field") or "label"
	show_currency = widget.get("show_currency_symbol")
	if show_currency is None:
		show_currency = True
	hint = render_hint or widget["widget_type"].lower()
	section_meta = _legacy_widget_section_meta(config)

	return {
		"widget_key": widget["key"],
		"widget_type": widget["widget_type"],
		"label": widget.get("label"),
		"chart": {
			"series": series,
			"metric": metric,
			"dimension": dimension,
			"filters": {},
			"show_currency_symbol": bool(show_currency),
		},
		"series": series,
		"data": {"series": series},
		"meta": {
			"schema_version": 1,
			"render_hint": hint,
			"dimension": dimension,
			"metric": metric,
			"count": len(series),
			"legacy_method": method_path,
			**section_meta,
		},
	}


def _legacy_chart_widget_payload(
	user: str,
	company: Optional[str],
	widget: dict[str, Any],
	limit: int,
	*,
	render_hint: Optional[str] = None,
) -> dict[str, Any]:
	config = widget.get("config") or {}
	method_path = config.get("legacy_method") or widget.get("legacy_method")
	if not method_path:
		frappe.throw(
			_("Widget {0} has no legacy_method configured").format(widget["key"]),
			frappe.ValidationError,
		)

	effective_limit = int(config.get("row_limit") or limit or 10)
	payload = _call_legacy_method(
		method_path,
		company=company,
		limit=effective_limit,
		extra=config.get("legacy_params"),
	)
	series = _legacy_series_compat(_legacy_series_from_payload(payload, config))
	metric = widget.get("metric_key") or config.get("metric") or "value"
	dimension = (
		widget.get("dimension_key")
		or config.get("dimension")
		or (payload.get("meta") or {}).get("dimension")
		or config.get("label_field")
		or "value"
	)
	show_currency = widget.get("show_currency_symbol")
	if show_currency is None:
		show_currency = True
	hint = render_hint or widget["widget_type"].lower()
	section_meta = _legacy_widget_section_meta(config)
	payload_meta = payload.get("meta") if isinstance(payload, dict) else {}
	api_chart_key = (payload_meta or {}).get("chart_key")
	config_chart_key = section_meta.get("chart_key")
	# Keep profile chart_key aliases — API meta may use short internal keys (e.g. "aging").
	safe_payload_meta = {
		k: v
		for k, v in (payload_meta or {}).items()
		if k not in ("schema_version", "chart_key")
	}

	result = {
		"widget_key": widget["key"],
		"widget_type": widget["widget_type"],
		"label": widget.get("label"),
		"chart": {
			"series": series,
			"metric": metric,
			"dimension": dimension,
			"filters": {},
			"show_currency_symbol": bool(show_currency),
		},
		"series": series,
		"data": {"series": series},
		"meta": {
			"schema_version": 1,
			"render_hint": hint,
			"dimension": dimension,
			"metric": metric,
			"count": len(series),
			**safe_payload_meta,
			**section_meta,
		},
	}
	if api_chart_key and config_chart_key and str(api_chart_key) != str(config_chart_key):
		result["_alias_keys"] = [str(api_chart_key).strip()]
	return result


def _legacy_table_widget_payload(
	user: str,
	company: Optional[str],
	widget: dict[str, Any],
	limit: int,
) -> dict[str, Any]:
	config = widget.get("config") or {}
	method_path = config.get("legacy_method") or widget.get("legacy_method")
	if not method_path:
		frappe.throw(
			_("Widget {0} has no legacy_method configured").format(widget["key"]),
			frappe.ValidationError,
		)

	payload = _call_legacy_method(
		method_path,
		company=company,
		limit=limit,
		extra=config.get("legacy_params"),
	)
	mode = (config.get("rows_mode") or "list").strip().lower()
	if mode == "dict_to_series":
		raw_rows = _legacy_series_from_payload(payload, config)
	else:
		raw_rows = _extract_rows(payload, config.get("rows_key") or "rows")
	row_limit = int(config.get("row_limit") or limit or 10)
	columns_cfg = config.get("columns") or []

	rows: list[dict[str, Any]] = []
	for raw in raw_rows[:row_limit]:
		if not isinstance(raw, dict):
			continue
		row_out: dict[str, Any] = {}
		for col in columns_cfg:
			key = col.get("key")
			field = col.get("field") or key
			if key and field:
				row_out[key] = raw.get(field)
		if row_out:
			rows.append(row_out)

	columns = columns_cfg if columns_cfg else _default_table_columns(compare=False)
	section_meta = _legacy_widget_section_meta(config)
	ranking_series = _legacy_ranking_series_from_table_rows(rows) if widget["widget_type"] == "RANKING" else []

	result: dict[str, Any] = {
		"widget_key": widget["key"],
		"widget_type": widget["widget_type"],
		"label": widget.get("label"),
		"table": {
			"columns": columns,
			"rows": rows,
			"show_currency_symbol": True,
		},
		"rows": rows,
		"data": {
			"rows": rows,
			"columns": columns,
		},
		"meta": {
			"schema_version": 1,
			"render_hint": "ranking" if widget["widget_type"] == "RANKING" else "table",
			**section_meta,
		},
	}
	if ranking_series:
		result["chart"] = {
			"series": ranking_series,
			"metric": widget.get("metric_key") or "value",
			"show_currency_symbol": True,
		}
		result["series"] = ranking_series
		result["data"]["series"] = ranking_series
	return result


def _legacy_widget_cache_key(
	widget_key: str,
	company: Optional[str],
	method_path: str,
	from_date: Optional[str],
	to_date: Optional[str],
	limit: int,
) -> str:
	return (
		f"mobile_legacy_widget:v{LEGACY_WIDGET_CACHE_VERSION}:{widget_key}:"
		f"{company or ''}:{method_path}:{from_date or ''}:{to_date or ''}:{limit}"
	)


def _legacy_widget_payload(
	user: str,
	company: Optional[str],
	widget: dict[str, Any],
	from_date: Optional[str],
	to_date: Optional[str],
	limit: int,
	extra: dict[str, Any],
) -> dict[str, Any]:
	config = widget.get("config") or {}
	method_path = config.get("legacy_method") or widget.get("legacy_method")
	if not method_path:
		frappe.throw(
			_("Widget {0} has no legacy API mapping").format(widget["key"]),
			frappe.ValidationError,
		)

	widget_key = (widget.get("key") or "").strip()
	legacy_cache_key = None
	if widget_key in _LEGACY_WIDGET_CACHE_KEYS:
		legacy_cache_key = _legacy_widget_cache_key(
			widget_key, company, method_path, from_date, to_date, limit
		)
		cached = frappe.cache().get_value(legacy_cache_key)
		if cached:
			return cached

	try:
		payload = _call_legacy_method(
			method_path,
			company=company,
			from_date=from_date,
			to_date=to_date,
			limit=limit,
		)
	except frappe.PermissionError:
		if (widget.get("key") or "") == "home_recent_activities":
			payload = {
				"items": [],
				"approvals": [],
				"total_pending": 0,
				"meta": {"schema_version": 1, "empty_reason": "approvals_not_permitted"},
			}
		else:
			raise

	section_meta = _legacy_widget_section_meta(config)
	result: dict[str, Any] = {
		"widget_key": widget["key"],
		"widget_type": widget.get("widget_type") or "LIST",
		"label": widget.get("label"),
		"data": payload,
		"meta": {
			"schema_version": 1,
			"legacy_method": method_path,
			"render_hint": "list",
			**section_meta,
		},
	}
	if widget.get("key") == "inventory_movement_insights" or "get_inventory_performance" in (method_path or ""):
		rows: list[dict[str, Any]] = []
		for item in (payload.get("fastMovingItems") or [])[: int(config.get("row_limit") or limit or 5)]:
			if not isinstance(item, dict):
				continue
			rows.append(
				{
					"label": item.get("itemName") or item.get("itemCode"),
					"value": float(item.get("value") or 0),
					"quantity": float(item.get("quantity") or 0),
					"item_code": item.get("itemCode"),
				}
			)
		series = [{"label": r["label"], "value": r["value"]} for r in rows if r.get("label")]
		result["rows"] = rows
		result["series"] = series
		result["meta"]["data_kind"] = "inventory_movement"
	if legacy_cache_key:
		frappe.cache().set_value(legacy_cache_key, result, expires_in_sec=LEGACY_WIDGET_CACHE_TTL)
	return result
