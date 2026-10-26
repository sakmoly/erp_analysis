"""
Sales By Division drill — single API for mobile (Division → sub_group → brand).

Always reads tabSalesDashBoard with applied division/sub_group filters.
Does not call get_product_performance or merge Sales Invoice lines.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Optional

import frappe
from frappe.utils import getdate

SALES_BY_DIVISION_DRILL_PATH = ("division", "sub_group", "brand")
WIDGET_KEY = "sales_by_division"
# Industrial division-wide Hitachi (~9.35M YTD) when sub_group filter is missing/ignored.
_DIVISION_WIDE_HITACHI_RATIO = 0.97


def _dashboard_scalar(
	*,
	company: Optional[str],
	from_date: date,
	to_date: date,
	filters: dict[str, list[Any]],
	brand: Optional[str] = None,
) -> float:
	if not frappe.db.table_exists("SalesDashBoard"):
		return 0.0
	params: list[Any] = [from_date, to_date]
	conditions = ["`Invoice_Date` BETWEEN %s AND %s"]
	divisions = [str(d).strip() for d in (filters.get("division") or []) if str(d).strip()]
	sub_groups = [str(s).strip() for s in (filters.get("sub_group") or []) if str(s).strip()]
	if divisions:
		ph = ", ".join(["%s"] * len(divisions))
		conditions.append(f"COALESCE(`Division`, '') IN ({ph})")
		params.extend(divisions)
	if sub_groups:
		ph = ", ".join(["%s"] * len(sub_groups))
		conditions.append(f"COALESCE(`Sub_Group`, '') IN ({ph})")
		params.extend(sub_groups)
	if brand:
		conditions.append("COALESCE(`Brand`, '') = %s")
		params.append(brand)
	territories = [str(t).strip() for t in (filters.get("territory") or []) if str(t).strip()]
	if territories and frappe.db.has_column("SalesDashBoard", "Territory"):
		ph = ", ".join(["%s"] * len(territories))
		conditions.append(f"COALESCE(`Territory`, '') IN ({ph})")
		params.extend(territories)
	if company and frappe.db.has_column("SalesDashBoard", "Company"):
		conditions.append("COALESCE(`Company`, '') = %s")
		params.append(company)
	row = frappe.db.sql(
		f"""
		SELECT COALESCE(SUM(`Net_Amount`), 0) AS total
		FROM `tabSalesDashBoard`
		WHERE {" AND ".join(conditions)}
		""",
		tuple(params),
		as_dict=True,
	)
	return float((row[0].get("total") if row else 0) or 0)


def assess_sub_group_drill_reconcile(
	*,
	company: Optional[str],
	from_date: date,
	to_date: date,
	filters: dict[str, list[Any]],
	rows: list[dict[str, Any]],
) -> dict[str, Any]:
	"""
	Depth-1 check: SUM(sub_group rows) should match SUM(Net_Amount) for filters.division.
	"""
	divisions = [str(d).strip() for d in (filters.get("division") or []) if str(d).strip()]
	if not divisions or not rows:
		return {}

	children_sum = round(
		sum(float(r.get("metric") or r.get("total_sales") or 0) for r in rows),
		2,
	)
	reconcile_filters = {
		k: v
		for k, v in filters.items()
		if k not in ("sub_group", "item_group", "group") and v
	}
	if "division" not in reconcile_filters:
		reconcile_filters["division"] = divisions
	division_total = round(
		_dashboard_scalar(
			company=company,
			from_date=from_date,
			to_date=to_date,
			filters=reconcile_filters,
		),
		2,
	)

	delta = round(children_sum - division_total, 2)
	tolerance = max(abs(division_total) * 0.005, 1.0)
	ok = abs(delta) <= tolerance
	return {
		"reconcile_ok": ok,
		"reconcile": {
			"division": divisions[0] if len(divisions) == 1 else divisions,
			"division_net_sales_total": division_total,
			"sub_group_rows_sum": children_sum,
			"delta": delta,
			"filters_applied": filters,
		},
	}


def assess_brand_drill_scope(
	*,
	company: Optional[str],
	from_date: date,
	to_date: date,
	filters: dict[str, list[Any]],
	rows: list[dict[str, Any]],
) -> dict[str, Any]:
	"""
	Mobile guard: ~9.35M Hitachi = division-wide brands; ~6.09M under Industrial Consumables is valid scoped.
	"""
	divisions = [str(d).strip() for d in (filters.get("division") or []) if str(d).strip()]
	sub_groups = [str(s).strip() for s in (filters.get("sub_group") or []) if str(s).strip()]
	top = rows[0] if rows else {}
	top_brand = str(top.get("label") or top.get("dimension_value") or "")
	top_sales = float(top.get("metric") or top.get("total_sales") or 0)

	division_wide_hitachi = 0.0
	if divisions:
		division_wide_hitachi = _dashboard_scalar(
			company=company,
			from_date=from_date,
			to_date=to_date,
			filters={"division": divisions},
			brand="Hitachi",
		)

	sub_group_total = 0.0
	if divisions and sub_groups:
		sub_group_total = _dashboard_scalar(
			company=company,
			from_date=from_date,
			to_date=to_date,
			filters={"division": divisions, "sub_group": sub_groups},
		)

	matches_division_wide = False
	if top_brand == "Hitachi" and division_wide_hitachi > 0 and top_sales > 0:
		matches_division_wide = top_sales >= division_wide_hitachi * _DIVISION_WIDE_HITACHI_RATIO

	scoped = bool(sub_groups) and bool(rows) and not matches_division_wide
	status = "scoped" if scoped else ("division_wide" if matches_division_wide else "unknown")

	return {
		"drill_scope_status": status,
		"accept_response": scoped,
		"is_division_wide_brand_mix": matches_division_wide,
		"scope_check": {
			"top_brand": top_brand or None,
			"top_brand_net_sales": round(top_sales, 2) if top_sales else None,
			"division_wide_hitachi_reference": round(division_wide_hitachi, 2)
			if division_wide_hitachi
			else None,
			"sub_group_net_sales_total": round(sub_group_total, 2) if sub_group_total else None,
			"matches_division_wide_hitachi": matches_division_wide,
			"filters_applied": filters,
		},
	}


def _normalize_row(raw: dict[str, Any]) -> dict[str, Any]:
	label = str(raw.get("dimension_value") or raw.get("dimension") or raw.get("label") or "")
	metric = float(raw.get("metric") or raw.get("metric_value") or raw.get("total_sales") or 0)
	gp = raw.get("gross_profit")
	if gp is None and raw.get("gp") is not None:
		gp = raw.get("gp")
	gp_f = float(gp) if gp is not None else None
	gp_pct = raw.get("gp_pct")
	if gp_pct is None and gp_f is not None and metric > 0:
		gp_pct = round(gp_f / metric * 100, 2)

	out: dict[str, Any] = {
		"key": label,
		"label": label,
		"name": label,
		"title": label,
		"dimension": label,
		"dimension_value": label,
		"metric": round(metric, 2),
		"total_sales": round(metric, 2),
		"rank": raw.get("rank"),
		"metric_ly": raw.get("metric_ly"),
		"change_pct": raw.get("change_pct"),
	}
	if gp_f is not None:
		out["gross_profit"] = round(gp_f, 2)
		out["gp"] = round(gp_f, 2)
	if gp_pct is not None:
		out["gp_pct"] = gp_pct
	return out


def get_sales_by_division_drill(
	user: Optional[str] = None,
	company: Optional[str] = None,
	*,
	period: Optional[str] = None,
	from_date: Optional[str] = None,
	to_date: Optional[str] = None,
	limit: int = 15,
	drill_depth: Optional[int] = None,
	dimension: Optional[str] = None,
	filters: Any = None,
	division: Any = None,
	sub_group: Any = None,
	**kwargs: Any,
) -> dict[str, Any]:
	"""
	Mobile entry: one request per drill step.

	drill_depth 0 → group by division
	drill_depth 1 → item groups under filters.division
	drill_depth 2 → brands under filters.division + filters.sub_group
	"""
	from erp_analysis.services.analytics_dimensions import parse_logical_filters
	from erp_analysis.services.mobile_widgets import get_dashboard_widget_data
	from erp_analysis.utils.rpc import get_arg, to_int

	user = user or frappe.session.user
	company = company or get_arg("company", kwargs.get("company"))
	limit = to_int(get_arg("limit", kwargs.get("limit") or limit), 15)
	period = get_arg("period", period or kwargs.get("period"))
	from_date = get_arg("from_date", from_date or kwargs.get("from_date"))
	to_date = get_arg("to_date", to_date or kwargs.get("to_date"))
	drill_depth = to_int(get_arg("drill_depth", drill_depth), None)
	dimension = get_arg("dimension", dimension or kwargs.get("dimension"))

	parsed = parse_logical_filters(get_arg("filters", filters or kwargs.get("filters"))) or {}
	div = get_arg("division", division or kwargs.get("division"))
	if div is not None:
		parsed.setdefault("division", [])
		vals = div if isinstance(div, (list, tuple)) else [div]
		for v in vals:
			text = str(v or "").strip()
			if text and text not in parsed["division"]:
				parsed["division"].append(text)
	sub = get_arg("sub_group", sub_group or kwargs.get("sub_group") or kwargs.get("item_group"))
	if sub is not None:
		parsed.setdefault("sub_group", [])
		vals = sub if isinstance(sub, (list, tuple)) else [sub]
		for v in vals:
			text = str(v or "").strip()
			if text and text not in parsed["sub_group"]:
				parsed["sub_group"].append(text)

	from erp_analysis.services.analytics_sales import _coalesce_dashboard_filter_keys

	parsed = _coalesce_dashboard_filter_keys(parsed)

	widget_payload = get_dashboard_widget_data(
		user=user,
		widget_key=WIDGET_KEY,
		company=company,
		from_date=from_date,
		to_date=to_date,
		limit=limit,
		dimension=dimension,
		filters=parsed or None,
		drill_depth=drill_depth,
		period=period,
		**kwargs,
	)

	table = widget_payload.get("table") or {}
	meta = dict(widget_payload.get("meta") or {})
	raw_rows = table.get("rows") or widget_payload.get("rows") or []
	rows = [_normalize_row(r) for r in raw_rows if isinstance(r, dict)]
	dim_key = (dim or "").strip().lower() if (dim := table.get("dimension") or meta.get("dimension")) else ""
	if dim_key in ("sub_group", "item_group", "group"):
		for row in rows:
			full = row["dimension_value"]
			row["sub_group"] = full
			row["item_group"] = full
			row["drill_filter"] = {"sub_group": [full]}
	applied = table.get("filters") or meta.get("filters") or parsed
	if isinstance(applied, dict):
		applied = _coalesce_dashboard_filter_keys(dict(applied))
	else:
		applied = parsed

	depth = meta.get("drill_depth")
	if depth is None and drill_depth is not None:
		depth = int(drill_depth)
	dim = table.get("dimension") or meta.get("dimension")
	next_dim = meta.get("next_dimension")
	drillable = bool(meta.get("drillable")) if meta.get("drillable") is not None else bool(next_dim)

	series = [
		{
			"label": row["label"],
			"value": row["metric"],
			"dimension_value": row["dimension_value"],
			"value_ly": row.get("metric_ly"),
			"change_pct": row.get("change_pct"),
			"gp_pct": row.get("gp_pct"),
		}
		for row in rows
	]

	from_date_parsed = getdate(meta.get("from_date") or from_date or frappe.utils.nowdate())
	to_date_parsed = getdate(meta.get("to_date") or to_date or frappe.utils.nowdate())
	scope_meta: dict[str, Any] = {}
	if (dim or "").strip().lower() == "brand" and isinstance(applied, dict):
		scope_meta = assess_brand_drill_scope(
			company=company,
			from_date=from_date_parsed,
			to_date=to_date_parsed,
			filters=applied,
			rows=rows,
		)
	elif (
		(dim or "").strip().lower() in ("sub_group", "item_group", "group")
		and isinstance(applied, dict)
		and applied.get("division")
	):
		scope_meta = assess_sub_group_drill_reconcile(
			company=company,
			from_date=from_date_parsed,
			to_date=to_date_parsed,
			filters=applied,
			rows=rows,
		)

	return {
		"widget_key": WIDGET_KEY,
		"data_source": "SalesDashBoard",
		**scope_meta,
		"drill_path": list(SALES_BY_DIVISION_DRILL_PATH),
		"drill_depth": depth,
		"dimension": dim,
		"next_dimension": next_dim,
		"drillable": drillable,
		"filters": applied,
		"period": period or meta.get("period"),
		"rows": rows,
		"chart": {
			"series": series,
			"dimension": dim,
			"metric": table.get("metric") or "net_sales",
			"filters": applied,
		},
		"series": series,
		"table": {
			**table,
			"rows": rows,
			"filters": applied,
			"dimension": dim,
		},
		"meta": {
			**meta,
			"schema_version": 2,
			"data_source": "SalesDashBoard",
			"drill_path": list(SALES_BY_DIVISION_DRILL_PATH),
			"drill_depth": depth,
			"dimension": dim,
			"next_dimension": next_dim,
			"drillable": drillable,
			"filters": applied,
			"empty_state": meta.get("empty_state"),
			"empty_message": meta.get("empty_message"),
			**scope_meta,
		},
	}
