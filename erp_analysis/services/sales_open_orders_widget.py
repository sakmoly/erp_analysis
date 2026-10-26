"""Mobile Sales Dashboard — open Sales Orders KPI drill (table payloads)."""

from __future__ import annotations

from typing import Any, Optional

import frappe

from erp_analysis.services.sales_orders import (
	get_open_sales_order_items,
	get_open_so_summary,
	list_open_sales_orders_for_drill,
)

_LEVEL1_COLUMNS = [
	{"key": "label", "label": "Sales Order", "flex": 1.2},
	{"key": "subtitle", "label": "Customer / delivery", "flex": 1.6},
	{
		"key": "pending_delivery_value",
		"label": "Pending delivery",
		"format": "currency_compact",
		"align": "right",
		"flex": 1,
	},
	{"key": "delivery_status", "label": "Status", "flex": 1},
]

_LEVEL2_COLUMNS = [
	{"key": "label", "label": "Item", "flex": 1.4},
	{"key": "subtitle", "label": "Delivery", "flex": 1.2},
	{"key": "item_code", "label": "Code", "flex": 0.9},
	{
		"key": "pending_qty",
		"label": "Pending",
		"format": "number",
		"align": "right",
		"flex": 0.7,
	},
	{
		"key": "value",
		"label": "Pending (SAR)",
		"format": "currency_compact",
		"align": "right",
		"flex": 1,
	},
]


def _drill_depth(drill_depth: Optional[int], config: dict[str, Any]) -> int:
	if drill_depth is not None:
		return int(drill_depth)
	return int(config.get("default_drill_depth") or 1)


def _format_date(value: Any) -> Optional[str]:
	if not value:
		return None
	text = str(value).strip()
	return text[:10] if text else None


def _level1_subtitle(order: dict[str, Any]) -> str:
	customer = (order.get("customer_name") or order.get("customer") or "").strip()
	delivery = _format_date(order.get("delivery_date"))
	if customer and delivery:
		return f"{customer} · Del {delivery}"
	if customer:
		return customer
	return delivery or ""


def _level2_subtitle(line: dict[str, Any]) -> str:
	code = (line.get("item_code") or "").strip()
	delivery = _format_date(line.get("delivery_date"))
	pending = line.get("pending_qty")
	pending_text = ""
	if pending is not None:
		uom = (line.get("uom") or "").strip()
		pending_text = f"{pending:g} {uom}".strip() if uom else f"{pending:g} pending"
	if delivery and pending_text:
		return f"Del {delivery} · {pending_text}"
	if delivery:
		return f"Del {delivery}"
	return pending_text or code


def _level1_row(order: dict[str, Any]) -> dict[str, Any]:
	so_name = order.get("sales_order") or order.get("name")
	pending = order.get("pending_delivery_value")
	subtitle = _level1_subtitle(order)
	delivery = _format_date(order.get("delivery_date"))
	customer_name = order.get("customer_name") or order.get("customer")
	return {
		"id": so_name,
		"label": so_name,
		"subtitle": subtitle,
		"description": subtitle,
		"secondary_label": subtitle,
		"customer_name": customer_name,
		"customer": order.get("customer"),
		"delivery_date": delivery,
		"value": pending,
		"metric": pending,
		"amount": pending,
		"pending_delivery_value": pending,
		**order,
		"meta": {
			"sales_order": so_name,
			"customer": order.get("customer"),
			"customer_name": customer_name,
			"delivery_date": delivery,
			"drillable": True,
		},
	}


def _level2_row(so_name: Optional[str], line: dict[str, Any]) -> dict[str, Any]:
	title = (line.get("item_name") or line.get("item_code") or "Item").strip()
	subtitle = _level2_subtitle(line)
	pending = line.get("pending_amount")
	delivery = _format_date(line.get("delivery_date"))
	row_id = line.get("so_detail") or f"{so_name}-{line.get('item_code')}"
	return {
		"id": row_id,
		"label": title,
		"subtitle": subtitle,
		"description": subtitle,
		"secondary_label": subtitle,
		"dimension": title,
		"item_code": line.get("item_code"),
		"item_name": line.get("item_name"),
		"delivery_date": delivery,
		"value": pending,
		"metric": pending,
		"amount": pending,
		"pending_amount": pending,
		**line,
		"meta": {
			"sales_order": so_name,
			"so_detail": line.get("so_detail"),
			"delivery_date": delivery,
		},
	}


def _list_series(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
	series: list[dict[str, Any]] = []
	for row in rows:
		series.append(
			{
				"label": row.get("label"),
				"subtitle": row.get("subtitle"),
				"value": row.get("value"),
				"dimension_value": row.get("id") or row.get("label"),
				"delivery_date": row.get("delivery_date"),
				"customer_name": row.get("customer_name"),
			}
		)
	return series


def _sales_order_from_filters(filters: Any) -> Optional[str]:
	from erp_analysis.services.analytics_dimensions import parse_logical_filters

	parsed = parse_logical_filters(filters)
	values = parsed.get("sales_order") or []
	for val in values:
		text = str(val or "").strip()
		if text:
			return text
	return None


def build_open_sales_orders_widget_payload(
	user: str,
	company: Optional[str],
	widget: dict[str, Any],
	*,
	limit: int,
	filters: Any = None,
	drill_depth: Optional[int] = None,
) -> dict[str, Any]:
	config = widget.get("config") or {}
	depth = _drill_depth(drill_depth, config)
	drill_path = config.get("drill_path") or ["sales_order", "item"]
	currency = frappe.get_cached_value("Company", company, "default_currency") if company else None
	list_layout = {
		"title_key": "label",
		"subtitle_key": "subtitle",
		"value_key": "value",
	}

	if depth >= 2:
		so_name = _sales_order_from_filters(filters)
		items_payload = get_open_sales_order_items(
			user=user,
			company=company,
			sales_order=so_name,
			filters=filters,
			limit=limit,
			pending_lines_only=True,
		)
		meta = items_payload.get("meta") or {}
		label = so_name or widget.get("label") or "Sales Order"
		rows = [_level2_row(so_name, line) for line in items_payload.get("items") or []]
		series = _list_series(rows)
		return {
			"widget_key": widget["key"],
			"widget_type": widget["widget_type"],
			"label": label,
			"drill_depth": 2,
			"drill_path": drill_path,
			"table": {
				"currency_display": {"show_symbol": False},
				"columns": config.get("columns") or _LEVEL2_COLUMNS,
				"rows": rows,
			},
			"rows": rows,
			"series": series,
			"chart": {"series": series, "show_currency_symbol": False},
			"data": {"rows": rows, "series": series},
			"meta": {
				"schema_version": 1,
				"render_hint": "ranking",
				"sales_order": so_name,
				"customer_name": meta.get("customer_name"),
				"delivery_date": meta.get("delivery_date"),
				"currency": meta.get("currency") or currency,
				"pending_delivery_value": meta.get("pending_delivery_value"),
				"open_so_value": meta.get("open_so_value"),
				"line_count": meta.get("line_count"),
				"drill_path": drill_path,
				"drill_depth": 2,
				"list_layout": list_layout,
			},
		}

	list_payload = list_open_sales_orders_for_drill(
		user=user,
		company=company,
		filters=filters,
		limit=limit,
	)
	summary = list_payload.get("meta") or {}
	rows = [_level1_row(order) for order in list_payload.get("orders") or []]
	series = _list_series(rows)

	return {
		"widget_key": widget["key"],
		"widget_type": widget["widget_type"],
		"label": widget.get("label") or "Open Sales Orders",
		"drill_depth": 1,
		"drill_path": drill_path,
		"table": {
			"currency_display": {"show_symbol": False},
			"columns": config.get("columns") or _LEVEL1_COLUMNS,
			"rows": rows,
		},
		"rows": rows,
		"series": series,
		"chart": {"series": series, "show_currency_symbol": False},
		"data": {"rows": rows, "series": series},
		"meta": {
			"schema_version": 1,
			"render_hint": "ranking",
			"total_rows": summary.get("total_rows"),
			"open_so_count": summary.get("open_so_count"),
			"open_so_value": summary.get("open_so_value"),
			"currency": summary.get("currency") or currency,
			"drill_path": drill_path,
			"drill_depth": 1,
			"date_scope": summary.get("date_scope") or "open_snapshot",
			"list_layout": list_layout,
		},
	}


def enrich_open_so_kpi_meta(
	kpi: dict[str, Any],
	*,
	user: str,
	company: Optional[str],
	filters: Any,
) -> dict[str, Any]:
	summary = get_open_so_summary(user=user, company=company, filters=filters)
	currency = summary.get("currency")
	out = dict(kpi)
	meta = dict(out.get("meta") or {})
	meta.update(
		{
			"open_so_count": summary.get("open_so_count"),
			"open_so_value": summary.get("open_so_value"),
			"currency": currency,
			"date_scope": summary.get("date_scope") or "open_snapshot",
		}
	)
	out["meta"] = meta
	if out.get("value") is None:
		out["value"] = summary.get("open_so_count")
	return out
