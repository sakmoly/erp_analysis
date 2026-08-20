"""Time-series sales trends for mobile dashboard LINE widgets."""

from __future__ import annotations

from datetime import date
from typing import Any, Optional

import frappe

from erp_analysis.permissions.access_profile import resolve_territory_scope, si_territory_sql
from erp_analysis.services.analytics_dimensions import parse_logical_filters, validate_logical_filters
from erp_analysis.services.sales_period import resolve_comparison_dates, resolve_period_dates, variance_block

ALLOWED_GROUP_BY = frozenset({"month", "week", "day", "quarter", "year"})
ALLOWED_METRICS = frozenset({"net_sales", "gross_sales", "transactions"})


def get_sales_trends(
	*,
	user: str,
	company: Optional[str] = None,
	from_date: Optional[str] = None,
	to_date: Optional[str] = None,
	group_by: str = "month",
	metric: str = "net_sales",
	filters: Any = None,
	compare: Optional[str] = None,
	period: Optional[str] = None,
) -> dict[str, Any]:
	metric = (metric or "net_sales").strip().lower()
	if metric not in ALLOWED_METRICS:
		frappe.throw(f"Unsupported trend metric: {metric}")

	group_key = (group_by or "month").strip().lower()
	if group_key not in ALLOWED_GROUP_BY:
		frappe.throw(f"Unsupported group_by: {group_by}")

	start, end, period_key = resolve_period_dates(from_date, to_date, period=period)
	parsed_filters = parse_logical_filters(filters)
	validated_filters = validate_logical_filters(user, company, parsed_filters)

	series = _query_trend_series(
		company=company,
		from_date=start,
		to_date=end,
		group_by=group_key,
		metric=metric,
		validated_filters=validated_filters,
	)
	comparison = None
	if compare:
		comp_start, comp_end = resolve_comparison_dates(start, end, compare, period_key=period_key)
		ly_series = _query_trend_series(
			company=company,
			from_date=comp_start,
			to_date=comp_end,
			group_by=group_key,
			metric=metric,
			validated_filters=validated_filters,
		)
		align_key = _series_align_key(group_key)
		ly_map = {row.get(align_key) or row["period"]: row["value"] for row in ly_series}
		for point in series:
			key = point.get(align_key) or point["period"]
			point["value_ly"] = ly_map.get(key)
			if point.get("value_ly") is not None:
				variance = variance_block(float(point.get("value") or 0), float(point["value_ly"]))
				point["change_pct"] = variance.get("change_pct")

		current_total = sum(float(row.get("value") or 0) for row in series)
		ly_total = sum(float(row.get("value_ly") or 0) for row in series if row.get("value_ly") is not None)
		comparison = {
			"value": round(current_total, 2),
			"value_ly": round(ly_total, 2),
			**variance_block(current_total, ly_total),
		}

	return {
		"series": series,
		"comparison": comparison,
		"meta": {
			"schema_version": 1,
			"metric": metric,
			"group_by": group_key,
			"from_date": str(start),
			"to_date": str(end),
			"period": period_key,
			"compare": compare,
			"company": company,
			"filters": parsed_filters,
		},
	}


def _query_trend_series(
	*,
	company: Optional[str],
	from_date: date,
	to_date: date,
	group_by: str,
	metric: str,
	validated_filters: list[tuple[dict[str, Any], list[Any]]],
) -> list[dict[str, Any]]:
	group_expr, label_expr = _group_expressions(group_by)
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
		placeholders = ", ".join(["%s"] * len(values))
		conditions.append(f"{f_alias}.`{f_field}` IN ({placeholders})")
		params.extend(values)

	metric_expr = "COALESCE(SUM(si.base_net_total), 0)"
	if metric == "gross_sales":
		metric_expr = "COALESCE(SUM(si.base_grand_total), 0)"
	elif metric == "transactions":
		metric_expr = "COUNT(DISTINCT si.name)"

	where_sql = " AND ".join(conditions)
	rows = frappe.db.sql(
		f"""
		SELECT
			{group_expr} AS period,
			{label_expr} AS label,
			{metric_expr} AS value
		FROM `tabSales Invoice` si
		WHERE {where_sql}
		GROUP BY period, label
		ORDER BY period
		""",
		tuple(params),
		as_dict=True,
	)

	out: list[dict[str, Any]] = []
	for row in rows:
		period = str(row.get("period") or "")
		label = row.get("label") or period
		point: dict[str, Any] = {
			"period": period,
			"label": str(label),
			"value": round(float(row.get("value") or 0), 2),
		}
		if group_by == "month" and period:
			point["month"] = period.split("-")[-1] if "-" in period else period
		out.append(point)
	return out


def _series_align_key(group_by: str) -> str:
	if group_by == "month":
		return "month"
	return "period"


def _group_expressions(group_by: str) -> tuple[str, str]:
	if group_by == "month":
		return (
			"DATE_FORMAT(si.posting_date, '%%Y-%%m')",
			"DATE_FORMAT(si.posting_date, '%%b')",
		)
	if group_by == "week":
		return (
			"DATE_FORMAT(si.posting_date, '%%x-W%%v')",
			"CONCAT('W', DATE_FORMAT(si.posting_date, '%%v'))",
		)
	if group_by == "day":
		return (
			"DATE(si.posting_date)",
			"DATE_FORMAT(si.posting_date, '%%d %%b')",
		)
	if group_by == "quarter":
		return (
			"CONCAT(YEAR(si.posting_date), '-Q', QUARTER(si.posting_date))",
			"CONCAT('Q', QUARTER(si.posting_date))",
		)
	return (
		"CAST(YEAR(si.posting_date) AS CHAR)",
		"CAST(YEAR(si.posting_date) AS CHAR)",
	)
