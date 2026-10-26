"""Generic sales analysis grouped by logical dimensions (Phase D)."""

from __future__ import annotations

from datetime import date
from typing import Any, Optional

import frappe
from frappe import _
from frappe.utils import getdate

from erp_analysis.permissions.access_profile import (
	bypass_view_territories,
	get_view_territories,
	resolve_territory_scope,
	si_territory_sql,
)
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
		"sales_return",
		"customer_count",
		"active_customers",
		"gross_profit",
		"gp_pct",
		"cogs",
	}
)

METRIC_LABELS = {
	"net_sales": "Net Sales",
	"gross_sales": "Gross Sales",
	"sales_qty": "Quantity Sold",
	"transactions": "Transactions",
	"average_transaction": "Average Transaction",
	"sales_return": "Sales Returns",
	"customer_count": "Active Customers",
	"active_customers": "Active Customers",
	"gross_profit": "Gross Profit",
	"gp_pct": "GP %",
	"cogs": "COGS",
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
	from erp_analysis.services.analytics_dimensions import normalize_division_slice_filters

	parsed_filters = normalize_division_slice_filters(user, company, parsed_filters)
	parsed_filters = _coalesce_dashboard_filter_keys(parsed_filters)
	validated_filters = validate_logical_filters(user, company, parsed_filters)
	compare_key = validate_compare(compare)

	rows = _query_sales_analysis(
		user=user,
		company=company,
		from_date=start,
		to_date=end,
		dimension_row=dim_row,
		dimension_key=dimension,
		metric=metric,
		validated_filters=validated_filters,
		limit=limit,
		order=order,
	)

	comp_start, comp_end = resolve_comparison_dates(start, end, compare_key, period_key=period_key)
	if compare_key:
		comp_rows = _query_sales_analysis(
			user=user,
			company=company,
			from_date=comp_start,
			to_date=comp_end,
			dimension_row=dim_row,
			dimension_key=dimension,
			metric=metric,
			validated_filters=validated_filters,
			limit=max(limit, 200),
			order=order,
		)
		rows = merge_compare_rows(rows, comp_rows)

	_attach_gp_metrics(
		user=user,
		company=company,
		from_date=start,
		to_date=end,
		dimension_key=(dimension or "").strip().lower(),
		dimension_row=dim_row,
		validated_filters=validated_filters,
		rows=rows,
	)

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
	if metric == "active_customers":
		metric = "customer_count"
	if metric not in ALLOWED_METRICS:
		frappe.throw(_("Unsupported metric: {0}").format(metric), frappe.ValidationError)

	start, end, period_key = resolve_period_dates(from_date, to_date, period=period)
	if from_date and to_date:
		period_key = "custom"

	parsed_filters = parse_logical_filters(filters)
	validated_filters = validate_logical_filters(user, company, parsed_filters)
	compare_key = validate_compare(compare)

	change_pct = None
	direction = "flat"

	if metric in ("gross_profit", "gp_pct", "cogs"):
		if metric == "cogs":
			value = _query_cogs_kpi(user, company, start, end, validated_filters)
			value_comparison = None
			if compare_key:
				comp_start, comp_end = resolve_comparison_dates(start, end, compare_key, period_key=period_key)
				value_comparison = _query_cogs_kpi(user, company, comp_start, comp_end, validated_filters)
		else:
			value = _query_gross_profit_kpi(user, company, start, end, metric, validated_filters)
			value_comparison = None
			if compare_key:
				comp_start, comp_end = resolve_comparison_dates(start, end, compare_key, period_key=period_key)
				value_comparison = _query_gross_profit_kpi(
					user, company, comp_start, comp_end, metric, validated_filters
				)
	else:
		value = _query_sales_kpi_total(
			user=user,
			company=company,
			from_date=start,
			to_date=end,
			metric=metric,
			validated_filters=validated_filters,
		)
		value_comparison = None
		if compare_key:
			comp_start, comp_end = resolve_comparison_dates(start, end, compare_key, period_key=period_key)
			value_comparison = _query_sales_kpi_total(
				user=user,
				company=company,
				from_date=comp_start,
				to_date=comp_end,
				metric=metric,
				validated_filters=validated_filters,
			)

	if compare_key and value_comparison is not None:
		variance = variance_block(value, value_comparison)
		change_pct = variance.get("change_pct")
		direction = variance.get("direction") or "flat"

	if metric in ("transactions", "customer_count"):
		fmt = "integer"
	elif metric == "gp_pct":
		fmt = "percent"
	elif metric in ("gross_profit", "sales_return", "cogs"):
		fmt = "currency_compact"
	else:
		fmt = "currency_compact"
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


def _territory_filtered_in_request(
	validated_filters: list[tuple[dict[str, Any], list[Any]]],
) -> bool:
	for filt_row, filt_values in validated_filters or []:
		if (filt_row.get("dimension_key") or "").strip().lower() == "territory" and filt_values:
			return True
	return False


def company_wide_sales_view(
	user: str,
	company: Optional[str],
	validated_filters: list[tuple[dict[str, Any], list[Any]]],
) -> bool:
	"""All Territories with allow_view_all_sales → company-wide SI / dashboard (no view_territories clip)."""
	if not bypass_view_territories("sales", user, company):
		return False
	return not _territory_filtered_in_request(validated_filters)


def company_wide_sales_view_for_filters(
	user: str,
	company: Optional[str],
	filters: Any,
) -> bool:
	parsed_filters = parse_logical_filters(filters)
	validated = validate_logical_filters(user, company, parsed_filters)
	return company_wide_sales_view(user, company, validated)


def _query_sales_kpi_total(
	*,
	user: Optional[str] = None,
	company: Optional[str],
	from_date: date,
	to_date: date,
	metric: str,
	validated_filters: list[tuple[dict[str, Any], list[Any]]],
) -> float:
	if metric in ("net_sales", "gross_sales", "transactions", "customer_count") and _dashboard_columns():
		return _query_dashboard_kpi_total(
			user, company, from_date, to_date, metric, validated_filters
		)

	metric_expr = _metric_expression(metric, "Sales Invoice")
	params: list[Any] = [from_date, to_date]
	conditions = ["si.docstatus = 1", "si.posting_date BETWEEN %s AND %s"]
	if company:
		conditions.append("si.company = %s")
		params.append(company)
	scope = resolve_territory_scope(
		user=user,
		company=company,
		purpose="view",
		module="sales",
	)
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
	if metric == "sales_return":
		return "COALESCE(SUM(CASE WHEN si.is_return = 1 THEN ABS(si.base_net_total) ELSE 0 END), 0)"
	if metric == "customer_count":
		return "COUNT(DISTINCT CASE WHEN si.is_return = 0 THEN si.customer END)"
	return "COALESCE(SUM(si.base_net_total), 0)"


def _resolve_kpi_territory_scope(
	user: Optional[str],
	company: Optional[str],
	validated_filters: list[tuple[dict[str, Any], list[Any]]],
) -> Optional[list[str]]:
	"""Territory scope for GP/COGS KPIs — same intent as SalesDashBoard dashboard KPIs."""
	territory_filtered = False
	territory_values: list[Any] = []
	for filt_row, filt_values in validated_filters or []:
		dim_key = (filt_row.get("dimension_key") or filt_row.get("key") or "").strip().lower()
		if dim_key == "territory" and filt_values:
			territory_filtered = True
			territory_values.extend(filt_values)
	if territory_values:
		return resolve_territory_scope(
			requested_list=[str(v) for v in territory_values if v is not None and str(v).strip()],
			user=user,
			company=company,
			purpose="view",
			module="sales",
		)
	return _dashboard_view_territory_scope(
		user,
		company,
		territory_filtered=territory_filtered,
	)


def _query_dashboard_profit_totals(
	user: Optional[str],
	company: Optional[str],
	from_date: date,
	to_date: date,
	validated_filters: list[tuple[dict[str, Any], list[Any]]],
) -> tuple[float, float, float, float]:
	"""Net sales, COGS, GP, GP% from SalesDashBoard with dashboard KPI filters."""
	cols = _dashboard_columns()
	cogs_col = _dashboard_cogs_column(cols)
	date_field = "Invoice_Date"
	metric_field = "Net_Amount"
	territory_field = "Territory"
	if not cols or not cogs_col or date_field not in cols or metric_field not in cols:
		return 0.0, 0.0, 0.0, 0.0

	where_sql, params = _dashboard_where_sql(
		user,
		company,
		from_date,
		to_date,
		validated_filters,
		date_field=date_field,
		territory_field=territory_field,
		cols=cols,
	)
	row = frappe.db.sql(
		f"""
		SELECT
			COALESCE(SUM(`{metric_field}`), 0) AS net_sales,
			COALESCE(SUM(`{cogs_col}`), 0) AS cogs
		FROM `tabSalesDashBoard`
		WHERE {where_sql}
		""",
		tuple(params),
		as_dict=True,
	)[0]
	net_sales = float(row.net_sales or 0)
	cogs = float(row.cogs or 0)
	gp = round(max(net_sales - cogs, 0), 2)
	gp_pct = round(gp / net_sales * 100, 2) if net_sales > 0 else 0.0
	return net_sales, cogs, gp, gp_pct


def _query_cogs_kpi(
	user: Optional[str],
	company: Optional[str],
	from_date: date,
	to_date: date,
	validated_filters: list[tuple[dict[str, Any], list[Any]]],
) -> float:
	"""COGS for KPI cards — same territory/date scope as net sales on SalesDashBoard."""
	cols = _dashboard_columns()
	if cols and _dashboard_cogs_column(cols):
		_, cogs, _, _ = _query_dashboard_profit_totals(
			user, company, from_date, to_date, validated_filters
		)
		return round(cogs, 2)

	from erp_analysis.services.kpi.gross_profit import _sales_and_cogs

	scope = _resolve_kpi_territory_scope(user, company, validated_filters)
	_, cogs = _sales_and_cogs(company, from_date, to_date, scope)
	return round(float(cogs or 0), 2)


def _query_gross_profit_kpi(
	user: Optional[str],
	company: Optional[str],
	from_date: date,
	to_date: date,
	metric: str,
	validated_filters: list[tuple[dict[str, Any], list[Any]]],
) -> float:
	cols = _dashboard_columns()
	if cols and _dashboard_cogs_column(cols):
		_, _, gp, gp_pct = _query_dashboard_profit_totals(
			user, company, from_date, to_date, validated_filters
		)
		if metric == "gp_pct":
			return gp_pct
		return gp

	from erp_analysis.services.kpi.gross_profit import _gp_block, _sales_and_cogs

	scope = _resolve_kpi_territory_scope(user, company, validated_filters)
	sales, cogs = _sales_and_cogs(company, from_date, to_date, scope)
	gp, gp_pct = _gp_block(sales, cogs)
	if metric == "gp_pct":
		return gp_pct
	return gp


def _needs_item_join(dimension_row: dict[str, Any], metric: str, validated_filters: list) -> bool:
	if dimension_row.get("analysis_source") == "dashboard":
		return False
	if dimension_row["analysis_doctype"] == "Sales Invoice Item":
		return True
	if metric == "sales_qty":
		return True
	return any(row["analysis_doctype"] == "Sales Invoice Item" for row, _ in validated_filters)


def _dashboard_columns() -> set[str]:
	if not frappe.db.table_exists("SalesDashBoard"):
		return set()
	try:
		return {c["Field"] for c in frappe.db.sql("SHOW COLUMNS FROM `tabSalesDashBoard`", as_dict=True)}
	except Exception:
		return set()


def _dashboard_view_territory_scope(
	user: Optional[str],
	company: Optional[str],
	*,
	territory_filtered: bool,
) -> Optional[list[str]]:
	"""
	Territory scope for SalesDashBoard widgets (Division drill, etc.).

	Mobile \"All Territories\" omits filters.territory:
	  - allow_view_all_sales → no territory SQL (company-wide dashboard rows)
	  - otherwise → view_territories from Access Profile
	"""
	if territory_filtered:
		return None
	user = user or frappe.session.user
	if bypass_view_territories("sales", user, company):
		return None
	profile_view = get_view_territories(user=user, company=company, expand=True)
	if profile_view:
		return profile_view
	return resolve_territory_scope(user=user, company=company, purpose="view", module="sales")


def _sub_group_label_variants(label: str) -> list[str]:
	"""Mobile UI labels e.g. 'Service (SE)' → also try 'Service'."""
	import re

	text = (label or "").strip()
	if not text:
		return []
	variants = [text]
	stripped = re.sub(r"\s*\([^)]*\)\s*$", "", text).strip()
	if stripped and stripped.lower() != text.lower():
		variants.append(stripped)
	return variants


def _sub_group_candidates(label: str, divisions: list[str]) -> list[str]:
	if not frappe.db.table_exists("SalesDashBoard") or not frappe.db.has_column("SalesDashBoard", "Sub_Group"):
		return []
	variants = _sub_group_label_variants(label)
	if not variants:
		return []
	match_parts: list[str] = []
	params: list[Any] = []
	for variant in variants:
		match_parts.append("COALESCE(`Sub_Group`, '') = %s")
		params.append(variant)
		match_parts.append("COALESCE(`Sub_Group`, '') LIKE %s")
		params.append(f"%{variant}%")
	division_sql = ""
	if divisions:
		cleaned = [str(d).strip() for d in divisions if d is not None and str(d).strip()]
		if cleaned:
			placeholders = ", ".join(["%s"] * len(cleaned))
			division_sql = f" AND COALESCE(`Division`, '') IN ({placeholders})"
			params.extend(cleaned)
	rows = frappe.db.sql(
		f"""
		SELECT DISTINCT COALESCE(`Sub_Group`, '') AS sub_group
		FROM `tabSalesDashBoard`
		WHERE COALESCE(`Sub_Group`, '') != ''
		  AND ({' OR '.join(match_parts)})
		  {division_sql}
		ORDER BY sub_group
		""",
		tuple(params),
		as_dict=True,
	)
	seen: set[str] = set()
	out: list[str] = []
	for row in rows:
		text = str(row.get("sub_group") or "").strip()
		if text and text not in seen:
			seen.add(text)
			out.append(text)
	return out


def _dashboard_sub_group_exists(division: str, sub_group: str) -> bool:
	if not frappe.db.table_exists("SalesDashBoard"):
		return False
	div = (division or "").strip()
	sg = (sub_group or "").strip()
	if not div or not sg:
		return False
	return bool(
		frappe.db.sql(
			"""
			SELECT 1
			FROM `tabSalesDashBoard`
			WHERE COALESCE(`Division`, '') = %s AND COALESCE(`Sub_Group`, '') = %s
			LIMIT 1
			""",
			(div, sg),
		)
	)


def _try_full_sub_group_name(label: str, divisions: list[str]) -> Optional[str]:
	"""
	Expand short mobile labels to dashboard Sub_Group (e.g. Consumables + Industrial
	→ Industrial Consumables).
	"""
	if not divisions:
		return None
	for variant in _sub_group_label_variants(label):
		for div in divisions:
			if _dashboard_sub_group_exists(div, variant):
				return variant
			composite = f"{div} {variant}".strip()
			if _dashboard_sub_group_exists(div, composite):
				return composite
	return None


def _infer_division_from_sub_groups(sub_groups: list[Any]) -> list[str]:
	"""When mobile omits division but sub_group is exact dashboard value (or unique match)."""
	if not frappe.db.table_exists("SalesDashBoard"):
		return []
	cleaned = [str(s).strip() for s in sub_groups if s is not None and str(s).strip()]
	if not cleaned:
		return []
	placeholders = ", ".join(["%s"] * len(cleaned))
	rows = frappe.db.sql(
		f"""
		SELECT DISTINCT COALESCE(`Division`, '') AS division
		FROM `tabSalesDashBoard`
		WHERE COALESCE(`Sub_Group`, '') IN ({placeholders})
		  AND COALESCE(`Division`, '') != ''
		""",
		tuple(cleaned),
		as_dict=True,
	)
	divisions = [str(r.get("division") or "").strip() for r in rows if str(r.get("division") or "").strip()]
	return divisions if len(divisions) == 1 else []


def _resolve_dashboard_sub_group_values(
	parsed: dict[str, list[Any]],
) -> dict[str, list[Any]]:
	"""
	Map mobile breadcrumb labels (e.g. \"Consumables\") to dashboard Sub_Group
	(e.g. \"Industrial Consumables\") when division scope is known.
	"""
	if not parsed.get("sub_group"):
		return parsed
	divisions = [str(d).strip() for d in (parsed.get("division") or []) if str(d).strip()]
	out = dict(parsed)
	resolved: list[str] = []
	for raw in out.get("sub_group") or []:
		text = str(raw or "").strip()
		if not text:
			continue
		full_name = _try_full_sub_group_name(text, divisions)
		if full_name:
			resolved.append(full_name)
			continue
		candidates = _sub_group_candidates(text, divisions)
		if text in candidates:
			resolved.append(text)
			continue
		if len(candidates) == 1:
			resolved.append(candidates[0])
			continue
		if len(candidates) > 1 and divisions:
			picked = None
			for div in divisions:
				div_l = div.lower()
				for candidate in candidates:
					c_l = candidate.lower()
					if c_l.startswith(div_l) or f"{div_l} " in c_l or candidate.startswith(f"{div} "):
						picked = candidate
						break
				if picked:
					break
			if not picked:
				for variant in _sub_group_label_variants(text):
					var_l = variant.lower()
					for candidate in candidates:
						if var_l and var_l in candidate.lower():
							picked = candidate
							break
					if picked:
						break
			resolved.append(picked or text)
			continue
		if len(candidates) > 1 and not divisions:
			resolved.append(text)
			continue
		resolved.append(text)
	if resolved:
		out["sub_group"] = list(dict.fromkeys(resolved))
	return out


def _coalesce_dashboard_filter_keys(parsed: dict[str, list[Any]]) -> dict[str, list[Any]]:
	"""Normalize logical filter keys for SalesDashBoard SQL."""
	if not parsed:
		return {}
	out = dict(parsed)
	if not out.get("division") and out.get("channel"):
		out["division"] = list(out["channel"])
	if not out.get("sub_group"):
		for alias in ("item_group", "group"):
			if out.get(alias):
				out["sub_group"] = list(out[alias])
				break
	out = _resolve_dashboard_sub_group_values(out)
	if not out.get("division") and out.get("sub_group"):
		inferred = _infer_division_from_sub_groups(out["sub_group"])
		if inferred:
			out["division"] = inferred
			out = _resolve_dashboard_sub_group_values(out)
	return out


def _dashboard_filter_column(
	dim_key: str,
	dim_row: dict[str, Any],
	cols: set[str],
	territory_field: str,
) -> Optional[str]:
	"""Map logical filter keys to SalesDashBoard column names."""
	from erp_analysis.services.analytics_dimensions import DIMENSION_KEY_ALIASES

	key = (dim_key or dim_row.get("dimension_key") or dim_row.get("key") or "").strip().lower()
	key = DIMENSION_KEY_ALIASES.get(key, key)
	if key == "territory" and territory_field in cols:
		return territory_field
	if dim_row.get("analysis_source") == "dashboard":
		field = (dim_row.get("analysis_field") or "").strip()
		if field and field in cols:
			return field
	static = {
		"division": "Division",
		"sub_group": "Sub_Group",
		"item_group": "Sub_Group",
		"group": "Sub_Group",
		"brand": "Brand",
		"salesperson": "Sales_Person",
	}
	col = static.get(key)
	if col and col in cols:
		return col
	return None


def _dashboard_metric_expression(metric: str, metric_field: str) -> str:
	if metric in ("net_sales", "gross_sales"):
		return f"COALESCE(SUM(`{metric_field}`), 0)"
	if metric == "transactions":
		invoice_col = "Invoice_No" if "Invoice_No" in _dashboard_columns() else "name"
		return f"COUNT(DISTINCT `{invoice_col}`)"
	if metric == "customer_count":
		customer_col = "Customer" if "Customer" in _dashboard_columns() else None
		if customer_col:
			return f"COUNT(DISTINCT `{customer_col}`)"
		return "0"
	frappe.throw(_("Unsupported metric for dashboard dimension: {0}").format(metric), frappe.ValidationError)


def _dashboard_cogs_column(cols: set[str]) -> Optional[str]:
	if "COGS" in cols:
		return "COGS"
	if "cogs" in cols:
		return "cogs"
	return None


def _dashboard_gp_group_field(dimension_key: str, dimension_row: dict[str, Any], cols: set[str]) -> Optional[str]:
	if dimension_row.get("analysis_source") == "dashboard":
		field = (dimension_row.get("analysis_field") or "").strip()
		return field if field in cols else None
	key = (dimension_key or "").strip().lower()
	if key == "territory" and "Territory" in cols:
		return "Territory"
	return None


def _query_dashboard_gp_map(
	*,
	user: Optional[str],
	company: Optional[str],
	from_date: date,
	to_date: date,
	group_field: str,
	validated_filters: list[tuple[dict[str, Any], list[Any]]],
) -> dict[str, dict[str, float]]:
	cols = _dashboard_columns()
	cogs_col = _dashboard_cogs_column(cols)
	if not cols or not cogs_col:
		return {}

	date_field = "Invoice_Date"
	metric_field = "Net_Amount"
	territory_field = "Territory"
	if date_field not in cols or metric_field not in cols or group_field not in cols:
		return {}

	group_expr = f"COALESCE(`{group_field}`, 'Unassigned')"
	where_sql, params = _dashboard_where_sql(
		user,
		company,
		from_date,
		to_date,
		validated_filters,
		date_field=date_field,
		territory_field=territory_field,
		cols=cols,
	)

	rows = frappe.db.sql(
		f"""
		SELECT
			{group_expr} AS dimension_value,
			COALESCE(SUM(`{metric_field}`), 0) AS net_sales,
			COALESCE(SUM(`{cogs_col}`), 0) AS cogs
		FROM `tabSalesDashBoard`
		WHERE {where_sql}
		GROUP BY {group_expr}
		""",
		tuple(params),
		as_dict=True,
	)

	out: dict[str, dict[str, float]] = {}
	for row in rows:
		label = str(row.get("dimension_value") or "Unassigned")
		net_sales = float(row.get("net_sales") or 0)
		cogs = float(row.get("cogs") or 0)
		gp = round(max(net_sales - cogs, 0), 2)
		gp_pct = round(gp / net_sales * 100, 2) if net_sales > 0 else 0.0
		out[label] = {"gross_profit": gp, "gp_pct": gp_pct}
	return out


def _attach_gp_metrics(
	*,
	user: Optional[str],
	company: Optional[str],
	from_date: date,
	to_date: date,
	dimension_key: str,
	dimension_row: dict[str, Any],
	validated_filters: list[tuple[dict[str, Any], list[Any]]],
	rows: list[dict[str, Any]],
) -> None:
	if not rows:
		return
	cols = _dashboard_columns()
	group_field = _dashboard_gp_group_field(dimension_key, dimension_row, cols)
	if not group_field:
		return
	gp_map = _query_dashboard_gp_map(
		user=user,
		company=company,
		from_date=from_date,
		to_date=to_date,
		group_field=group_field,
		validated_filters=validated_filters,
	)
	if not gp_map:
		return
	for row in rows:
		if row.get("gp_pct") is not None and row.get("gross_profit") is not None:
			continue
		key = str(row.get("dimension_value") if row.get("dimension_value") is not None else row.get("label") or "")
		info = gp_map.get(key) or gp_map.get(str(row.get("label") or ""))
		if not info:
			continue
		row["gross_profit"] = info["gross_profit"]
		row["gp_pct"] = info["gp_pct"]


def _dashboard_where_sql(
	user: Optional[str],
	company: Optional[str],
	from_date: date,
	to_date: date,
	validated_filters: list[tuple[dict[str, Any], list[Any]]],
	*,
	date_field: str,
	territory_field: str,
	cols: set[str],
) -> tuple[str, list[Any]]:
	"""Shared SalesDashBoard filters: dates, logical filters, view territory scope."""
	params: list[Any] = [from_date, to_date]
	conditions = [f"`{date_field}` BETWEEN %s AND %s"]

	if company and "Company" in cols:
		conditions.append("`Company` = %s")
		params.append(company)

	territory_filtered = False
	for filt_row, filt_values in validated_filters or []:
		dim_key = (filt_row.get("dimension_key") or filt_row.get("key") or "").strip().lower()
		col = _dashboard_filter_column(dim_key, filt_row, cols, territory_field)
		if not col:
			continue
		if dim_key == "territory":
			territory_filtered = True
		placeholders = ", ".join(["%s"] * len(filt_values))
		conditions.append(f"`{col}` IN ({placeholders})")
		params.extend([str(v) for v in filt_values if v is not None and str(v).strip()])

	scope = _dashboard_view_territory_scope(user, company, territory_filtered=territory_filtered)
	if scope and territory_field in cols:
		terr_sql, terr_params = si_territory_sql(scope, field=f"`{territory_field}`")
		if terr_sql:
			conditions.append(terr_sql.strip().lstrip("AND ").strip())
			params.extend(terr_params)

	return " AND ".join(conditions), params


def _query_dashboard_kpi_total(
	user: Optional[str],
	company: Optional[str],
	from_date: date,
	to_date: date,
	metric: str,
	validated_filters: list[tuple[dict[str, Any], list[Any]]],
) -> float:
	cols = _dashboard_columns()
	if not cols:
		return 0.0

	date_field = "Invoice_Date"
	metric_field = "Net_Amount"
	territory_field = "Territory"
	if date_field not in cols or metric_field not in cols:
		return 0.0

	metric_expr = _dashboard_metric_expression(metric, metric_field)
	where_sql, params = _dashboard_where_sql(
		user,
		company,
		from_date,
		to_date,
		validated_filters,
		date_field=date_field,
		territory_field=territory_field,
		cols=cols,
	)

	val = frappe.db.sql(
		f"SELECT {metric_expr} FROM `tabSalesDashBoard` WHERE {where_sql}",
		tuple(params),
	)[0][0]
	return float(val or 0)


def get_dashboard_sales_kpi(
	user: str,
	company: Optional[str] = None,
	metric: str = "net_sales",
	from_date: Optional[str] = None,
	to_date: Optional[str] = None,
	period: Optional[str] = "mtd",
	filters: Any = None,
	compare: Optional[str] = None,
) -> dict[str, Any]:
	"""Scalar KPI from SalesDashBoard (same scope/filters as division ranking widgets)."""
	metric = (metric or "net_sales").strip().lower()
	if metric not in ("net_sales", "gross_sales", "transactions", "customer_count"):
		frappe.throw(_("Unsupported dashboard KPI metric: {0}").format(metric), frappe.ValidationError)

	start, end, period_key = resolve_period_dates(from_date, to_date, period=period)
	if from_date and to_date:
		period_key = "custom"

	parsed_filters = parse_logical_filters(filters)
	validated_filters = validate_logical_filters(user, company, parsed_filters)
	compare_key = validate_compare(compare)

	value = _query_dashboard_kpi_total(user, company, start, end, metric, validated_filters)
	value_comparison = None
	if compare_key:
		comp_start, comp_end = resolve_comparison_dates(start, end, compare_key, period_key=period_key)
		value_comparison = _query_dashboard_kpi_total(
			user, company, comp_start, comp_end, metric, validated_filters
		)

	change_pct = None
	direction = "flat"
	if compare_key and value_comparison is not None:
		variance = variance_block(value, value_comparison)
		change_pct = variance.get("change_pct")
		direction = variance.get("direction") or "flat"

	if metric in ("transactions", "customer_count"):
		fmt = "integer"
	else:
		fmt = "currency_compact"

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
			"data_source": "dashboard",
		},
	}


def _query_dashboard_analysis(
	*,
	user: Optional[str],
	company: Optional[str],
	from_date: date,
	to_date: date,
	dimension_row: dict[str, Any],
	metric: str,
	validated_filters: list[tuple[dict[str, Any], list[Any]]],
	limit: int,
	order: str,
) -> list[dict[str, Any]]:
	join_path = dimension_row.get("join_path") or {}
	cols = _dashboard_columns()
	if not cols:
		return []

	date_field = join_path.get("date_field") or "Invoice_Date"
	metric_field = join_path.get("metric_field") or "Net_Amount"
	group_field = dimension_row.get("analysis_field")
	territory_field = join_path.get("territory_field") or "Territory"
	min_metric = float(join_path.get("min_metric") or 0)

	if not group_field or group_field not in cols:
		frappe.throw(_("Dimension field not available for analysis"))

	if date_field not in cols or metric_field not in cols:
		frappe.throw(_("Sales dashboard table is missing required columns"))

	date_expr = f"`{date_field}`"
	metric_expr = _dashboard_metric_expression(metric, metric_field)
	group_expr = f"COALESCE(`{group_field}`, 'Unassigned')"

	where_sql, params = _dashboard_where_sql(
		user,
		company,
		from_date,
		to_date,
		validated_filters,
		date_field=date_field,
		territory_field=territory_field,
		cols=cols,
	)
	params.append(limit)
	having_sql = f"HAVING metric_value > {min_metric}" if min_metric else "HAVING dimension_value IS NOT NULL AND dimension_value != ''"

	cogs_col = _dashboard_cogs_column(cols)
	gp_select = ""
	if cogs_col and metric_field in cols:
		gp_select = f", COALESCE(SUM(`{cogs_col}`), 0) AS cogs_value"

	rows = frappe.db.sql(
		f"""
		SELECT
			{group_expr} AS dimension_value,
			{metric_expr} AS metric_value
			{gp_select}
		FROM `tabSalesDashBoard`
		WHERE {where_sql}
		GROUP BY {group_expr}
		{having_sql}
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
		entry: dict[str, Any] = {
			"dimension_value": value,
			"label": str(value),
			"metric_value": round(metric_value, 2),
			"rank": idx,
		}
		if cogs_col and "cogs_value" in row:
			cogs = float(row.get("cogs_value") or 0)
			gp = round(max(metric_value - cogs, 0), 2)
			entry["gross_profit"] = gp
			entry["gp_pct"] = round(gp / metric_value * 100, 2) if metric_value > 0 else 0.0
		out.append(entry)
	return out


def _query_sales_analysis(
	*,
	user: Optional[str],
	company: Optional[str],
	from_date: date,
	to_date: date,
	dimension_row: dict[str, Any],
	dimension_key: Optional[str] = None,
	metric: str,
	validated_filters: list[tuple[dict[str, Any], list[Any]]],
	limit: int,
	order: str,
) -> list[dict[str, Any]]:
	if dimension_row.get("analysis_source") == "dashboard":
		return _query_dashboard_analysis(
			user=user,
			company=company,
			from_date=from_date,
			to_date=to_date,
			dimension_row=dimension_row,
			metric=metric,
			validated_filters=validated_filters,
			limit=limit,
			order=order,
		)

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

	scope = resolve_territory_scope(
		user=user,
		company=company,
		purpose="view",
		module="sales",
	)
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
