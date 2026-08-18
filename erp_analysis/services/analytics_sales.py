"""Generic sales analysis grouped by logical dimensions (Phase D)."""

from __future__ import annotations

from datetime import date
from typing import Any, Optional

import frappe
from frappe import _
from frappe.utils import getdate

from erp_analysis.permissions.access_profile import resolve_territory_scope, si_territory_sql
from erp_analysis.services.analytics_dimensions import (
	parse_logical_filters,
	resolve_effective_dimension,
	validate_logical_filters,
)
from erp_analysis.services.sales_period import (
	merge_compare_rows,
	pct_change,
	resolve_comparison_dates,
	resolve_period_dates,
	validate_compare,
	variance_block,
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
	period: Optional[str] = None,
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

	start, end, period_key = resolve_period_dates(from_date, to_date, period=period)
	limit = max(1, min(int(limit or 50), 200))
	order = "ASC" if (order or "desc").lower() == "asc" else "DESC"

	parsed_filters = parse_logical_filters(filters)
	validated_filters = validate_logical_filters(user, company, parsed_filters)
	compare_key = validate_compare(compare)

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

	comp_start, comp_end = resolve_comparison_dates(start, end, compare_key, period_key=period_key)
	if compare_key:
		comp_rows = _query_sales_analysis(
			company=company,
			from_date=comp_start,
			to_date=comp_end,
			dimension_row=dim_row,
			metric=metric,
			validated_filters=validated_filters,
			limit=max(limit, 200),
			order=order,
		)
		rows = merge_compare_rows(rows, comp_rows)

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
			"period": period_key,
			"compare_from_date": str(comp_start) if compare_key else None,
			"compare_to_date": str(comp_end) if compare_key else None,
		},
	}


def get_sales_kpi(
	user: str,
	company: Optional[str] = None,
	metric: str = "net_sales",
	from_date: Optional[str] = None,
	to_date: Optional[str] = None,
	period: Optional[str] = "mtd",
	filters: Any = None,
	compare: Optional[str] = None,
) -> dict[str, Any]:
	"""Scalar sales KPI for a period with optional comparison."""
	metric = (metric or "net_sales").strip().lower()
	if metric not in ALLOWED_METRICS:
		frappe.throw(_("Unsupported metric: {0}").format(metric), frappe.ValidationError)

	start, end, period_key = resolve_period_dates(from_date, to_date, period=period)
	if from_date and to_date:
		period_key = "custom"

	parsed_filters = parse_logical_filters(filters)
	validated_filters = validate_logical_filters(user, company, parsed_filters)
	compare_key = validate_compare(compare)

	value = _query_sales_kpi_total(
		company=company,
		from_date=start,
		to_date=end,
		metric=metric,
		validated_filters=validated_filters,
	)
	value_comparison = None
	change_pct = None
	direction = "flat"
	variance = None

	comp_start, comp_end = resolve_comparison_dates(start, end, compare_key, period_key=period_key)
	if compare_key:
		value_comparison = _query_sales_kpi_total(
			company=company,
			from_date=comp_start,
			to_date=comp_end,
			metric=metric,
			validated_filters=validated_filters,
		)
		variance = variance_block(value, value_comparison)
		change_pct = variance.get("change_pct")
		direction = variance.get("direction") or "flat"

	fmt = "integer" if metric == "transactions" else "currency_compact"
	return {
		"metric": metric,
		"label": METRIC_LABELS.get(metric, metric.replace("_", " ").title()),
		"value": round(value, 2),
		"value_ly": round(value_comparison, 2) if value_comparison is not None else None,
		"change_pct": change_pct,
		"direction": direction,
		"meta": {
			"schema_version": 1,
			"format": fmt,
			"from_date": str(start),
			"to_date": str(end),
			"period": period_key,
			"compare": compare_key,
			"company": company,
			"filters": parsed_filters,
		},
	}


def _query_sales_kpi_total(
	*,
	company: Optional[str],
	from_date: date,
	to_date: date,
	metric: str,
	validated_filters: list[tuple[dict[str, Any], list[Any]]],
) -> float:
	metric_expr = _metric_expression(metric, "Sales Invoice")
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
	join_sql = ""
	if metric == "sales_qty" or any(row[0]["analysis_doctype"] == "Sales Invoice Item" for row in validated_filters):
		join_sql = " INNER JOIN `tabSales Invoice Item` sii ON sii.parent = si.name "
	for row, values in validated_filters:
		f_alias = row["sql_alias"]
		f_field = row["analysis_field"]
		if not has_column(row["analysis_doctype"], f_field):
			frappe.throw(_("Filter dimension not available on site"))
		placeholders = ", ".join(["%s"] * len(values))
		conditions.append(f"{f_alias}.`{f_field}` IN ({placeholders})")
		params.extend(values)
	where_sql = " AND ".join(conditions)
	val = frappe.db.sql(
		f"SELECT {metric_expr} FROM `tabSales Invoice` si {join_sql} WHERE {where_sql}",
		tuple(params),
	)[0][0]
	return float(val or 0)


def _pct_change(current: float, previous: float) -> Optional[float]:
	return pct_change(current, previous)


def _merge_compare_ly(
	current_rows: list[dict[str, Any]],
	ly_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
	return merge_compare_rows(current_rows, ly_rows)


def _resolve_dates(from_date: Optional[str], to_date: Optional[str]) -> tuple[date, date]:
	start, end, _ = resolve_period_dates(from_date, to_date)
	return start, end


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
