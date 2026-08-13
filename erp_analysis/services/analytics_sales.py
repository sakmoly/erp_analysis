"""Generic sales analysis grouped by logical dimensions (Phase D)."""

from __future__ import annotations

from datetime import date
from typing import Any, Optional

import frappe
from frappe import _
from frappe.utils import add_years, get_first_day, getdate, nowdate

from erp_analysis.permissions.access_profile import resolve_territory_scope, si_territory_sql
from erp_analysis.services.analytics_dimensions import (
	parse_logical_filters,
	resolve_effective_dimension,
	validate_logical_filters,
)
from erp_analysis.utils.schema import has_column

ALLOWED_METRICS = frozenset(
	{
		"net_sales",
		"gross_sales",
		"sales_qty",
		"transactions",
		"average_transaction",
	}
)

METRIC_LABELS = {
	"net_sales": "Net Sales",
	"gross_sales": "Gross Sales",
	"sales_qty": "Quantity Sold",
	"transactions": "Transactions",
	"average_transaction": "Average Transaction",
}


ALLOWED_COMPARE = frozenset({"ly"})


def get_sales_analysis(
	user: str,
	company: Optional[str] = None,
	from_date: Optional[str] = None,
	to_date: Optional[str] = None,
	dimension: Optional[str] = None,
	secondary_dimension: Optional[str] = None,
	metric: str = "net_sales",
	filters: Any = None,
	limit: int = 50,
	order: str = "desc",
	compare: Optional[str] = None,
) -> dict[str, Any]:
	if secondary_dimension:
		frappe.throw(_("secondary_dimension is not supported yet"), frappe.ValidationError)

	if not dimension:
		frappe.throw(_("dimension is required"), frappe.ValidationError)

	metric = (metric or "net_sales").strip().lower()
	if metric not in ALLOWED_METRICS:
		frappe.throw(_("Unsupported metric: {0}").format(metric), frappe.ValidationError)

	dim_row = resolve_effective_dimension(user, company, dimension)
	if not dim_row.get("allow_group_by"):
		frappe.throw(_("Dimension {0} is not groupable").format(dimension), frappe.ValidationError)

	start, end = _resolve_dates(from_date, to_date)
	limit = max(1, min(int(limit or 50), 200))
	order = "ASC" if (order or "desc").lower() == "asc" else "DESC"

	parsed_filters = parse_logical_filters(filters)
	validated_filters = validate_logical_filters(user, company, parsed_filters)
	compare_key = (compare or "").strip().lower() or None
	if compare_key and compare_key not in ALLOWED_COMPARE:
		frappe.throw(_("Unsupported compare mode: {0}").format(compare), frappe.ValidationError)

	rows = _query_sales_analysis(
		company=company,
		from_date=start,
		to_date=end,
		dimension_row=dim_row,
		metric=metric,
		validated_filters=validated_filters,
		limit=limit,
		order=order,
	)

	if compare_key == "ly":
		ly_start = add_years(start, -1)
		ly_end = add_years(end, -1)
		ly_rows = _query_sales_analysis(
			company=company,
			from_date=ly_start,
			to_date=ly_end,
			dimension_row=dim_row,
			metric=metric,
			validated_filters=validated_filters,
			limit=max(limit, 200),
			order=order,
		)
		rows = _merge_compare_ly(rows, ly_rows)

	return {
		"data": rows,
		"meta": {
			"schema_version": 1,
			"from_date": str(start),
			"to_date": str(end),
			"dimension": dimension,
			"metric": metric,
			"metric_label": METRIC_LABELS.get(metric, metric),
			"company": company,
			"count": len(rows),
			"filters": parsed_filters,
			"compare": compare_key,
			"compare_from_date": str(add_years(start, -1)) if compare_key == "ly" else None,
			"compare_to_date": str(add_years(end, -1)) if compare_key == "ly" else None,
		},
	}


def _pct_change(current: float, previous: float) -> Optional[float]:
	if previous <= 0:
		return None if current <= 0 else 100.0
	return round((current - previous) / previous * 100, 2)


def _merge_compare_ly(
	current_rows: list[dict[str, Any]],
	ly_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
	ly_map = {
		str(row.get("dimension_value")): float(row.get("metric_value") or 0)
		for row in ly_rows
		if row.get("dimension_value") not in (None, "")
	}
	for row in current_rows:
		dim_val = row.get("dimension_value")
		current = float(row.get("metric_value") or 0)
		if dim_val is None or str(dim_val) == "":
			continue
		ly_val = ly_map.get(str(dim_val))
		row["metric_value_ly"] = round(ly_val, 2) if ly_val is not None else None
		row["change_pct"] = _pct_change(current, ly_val) if ly_val is not None else None
	return current_rows


def _resolve_dates(from_date: Optional[str], to_date: Optional[str]) -> tuple[date, date]:
	if from_date and to_date:
		return getdate(from_date), getdate(to_date)
	if from_date:
		return getdate(from_date), getdate(nowdate())
	end = getdate(to_date or nowdate())
	return get_first_day(end), end


def _metric_expression(metric: str, analysis_doctype: str) -> str:
	on_si = analysis_doctype == "Sales Invoice"
	if metric == "net_sales":
		return "COALESCE(SUM(si.base_net_total), 0)" if on_si else "COALESCE(SUM(sii.base_net_amount), 0)"
	if metric == "gross_sales":
		if on_si:
			return "COALESCE(SUM(si.base_grand_total), 0)"
		return "COALESCE(SUM(sii.base_amount), 0)"
	if metric == "sales_qty":
		return "COALESCE(SUM(sii.qty), 0)"
	if metric == "transactions":
		return "COUNT(DISTINCT si.name)"
	if metric == "average_transaction":
		return "COALESCE(SUM(si.base_net_total) / NULLIF(COUNT(DISTINCT si.name), 0), 0)"
	return "COALESCE(SUM(si.base_net_total), 0)"


def _needs_item_join(dimension_row: dict[str, Any], metric: str, validated_filters: list) -> bool:
	if dimension_row["analysis_doctype"] == "Sales Invoice Item":
		return True
	if metric == "sales_qty":
		return True
	return any(row["analysis_doctype"] == "Sales Invoice Item" for row, _ in validated_filters)


def _query_sales_analysis(
	*,
	company: Optional[str],
	from_date: date,
	to_date: date,
	dimension_row: dict[str, Any],
	metric: str,
	validated_filters: list[tuple[dict[str, Any], list[Any]]],
	limit: int,
	order: str,
) -> list[dict[str, Any]]:
	field = dimension_row["analysis_field"]
	alias = dimension_row["sql_alias"]

	if not has_column(dimension_row["analysis_doctype"], field):
		frappe.throw(_("Dimension field not available for analysis"))

	group_expr = f"{alias}.`{field}`"
	metric_expr = _metric_expression(metric, dimension_row["analysis_doctype"])

	params: list[Any] = [from_date, to_date]
	conditions = ["si.docstatus = 1", "si.posting_date BETWEEN %s AND %s"]

	if company:
		conditions.append("si.company = %s")
		params.append(company)

	scope = resolve_territory_scope(company=company, purpose="view", module="sales")
	terr_sql, terr_params = si_territory_sql(scope, field="si.territory")
	if terr_sql:
		conditions.append(terr_sql.strip().lstrip("AND ").strip())
		params.extend(terr_params)

	for row, values in validated_filters:
		f_alias = row["sql_alias"]
		f_field = row["analysis_field"]
		if not has_column(row["analysis_doctype"], f_field):
			frappe.throw(_("Filter dimension not available on site"))
		placeholders = ", ".join(["%s"] * len(values))
		conditions.append(f"{f_alias}.`{f_field}` IN ({placeholders})")
		params.extend(values)

	join_sql = ""
	if _needs_item_join(dimension_row, metric, validated_filters):
		join_sql = " INNER JOIN `tabSales Invoice Item` sii ON sii.parent = si.name "

	where_sql = " AND ".join(conditions)
	params.append(limit)

	rows = frappe.db.sql(
		f"""
		SELECT
			{group_expr} AS dimension_value,
			{metric_expr} AS metric_value
		FROM `tabSales Invoice` si
		{join_sql}
		WHERE {where_sql}
		GROUP BY {group_expr}
		HAVING dimension_value IS NOT NULL AND dimension_value != ''
		ORDER BY metric_value {order}
		LIMIT %s
		""",
		tuple(params),
		as_dict=True,
	)

	out: list[dict[str, Any]] = []
	for idx, row in enumerate(rows, start=1):
		value = row.get("dimension_value")
		metric_value = float(row.get("metric_value") or 0)
		out.append(
			{
				"dimension_value": value,
				"label": str(value),
				"metric_value": round(metric_value, 2),
				"rank": idx,
			}
		)
	return out
