"""Salesperson and product performance rankings (actuals only — no targets)."""

from __future__ import annotations

from datetime import date
from typing import Any, List, Optional

import frappe
from frappe.utils import add_days, add_months, get_first_day, get_last_day, getdate, nowdate

from erp_analysis.permissions.access_profile import si_territory_sql
from erp_analysis.utils.salesperson import resolve_salesperson_name


def _dashboard_territory_sql(
	territories: Optional[List[str]],
	cols: set[str],
) -> tuple[str, list[Any]]:
	if not territories:
		return "", []
	for candidate in ("Territory", "territory"):
		if candidate in cols:
			field = f"`{candidate}`"
			return si_territory_sql(territories, field=field)
	return "", []


def _si_territory_sql(territories: Optional[List[str]]) -> tuple[str, list[Any]]:
	return si_territory_sql(territories, field="si.territory")


SALESPERSON_ROW_FIELDS = (
	"salesperson",
	"total_sales",
	"invoice_count",
	"rank",
	"gp",
	"gp_pct",
	"collection",
	"outstanding",
	"overdue",
	"sales_ly",
	"growth_pct",
)

PRODUCT_ROW_FIELDS = (
	"key",
	"label",
	"total_sales",
	"sold_qty",
	"invoice_count",
	"rank",
	"gp",
	"gp_pct",
	"customer_count",
	"sales_ly",
	"growth_pct",
	"asp",
)


def _period_bounds(
	period: Optional[str] = None,
	from_date: Optional[str] = None,
	to_date: Optional[str] = None,
) -> tuple[date, date]:
	"""Resolve filter window — explicit from_date/to_date always wins over period."""
	if from_date and to_date:
		return getdate(from_date), getdate(to_date)
	if from_date:
		return getdate(from_date), getdate(to_date or nowdate())

	end = getdate(to_date or nowdate())
	period_key = (period or "mtd").lower().replace(" ", "_").replace("-", "_")

	if period_key == "today":
		return end, end
	if period_key == "yesterday":
		day = add_days(end, -1)
		return day, day
	if period_key in ("prev_month", "previous_month", "last_month"):
		prev = add_months(get_first_day(end), -1)
		return prev, get_last_day(prev)
	if period_key == "ytd":
		return date(end.year, 1, 1), end
	return get_first_day(end), end


def _norm_salesperson(name: Optional[str]) -> str:
	return (name or "Unassigned").strip() or "Unassigned"


def _map_get_float(values: dict[str, float], salesperson: str) -> float:
	key = _norm_salesperson(salesperson)
	if key in values:
		return values[key]
	return float(values.get(salesperson or "", 0.0) or 0.0)


def _map_get_ar(values: dict[str, dict[str, float]], salesperson: str) -> dict[str, float]:
	key = _norm_salesperson(salesperson)
	if key in values:
		return values[key]
	return values.get(salesperson or "", {"outstanding": 0.0, "overdue": 0.0})


def _dashboard_columns() -> set[str]:
	if not frappe.db.table_exists("SalesDashBoard"):
		return set()
	try:
		return {c["Field"] for c in frappe.db.sql("SHOW COLUMNS FROM `tabSalesDashBoard`", as_dict=True)}
	except Exception:
		return set()


def _company_filter_dashboard(company: Optional[str], cols: set[str]) -> tuple[str, list[Any]]:
	if company and "company" in cols:
		return " AND company = %s", [company]
	return "", []


def _ly_period(start: date, end: date) -> tuple[date, date]:
	return getdate(add_months(start, -12)), getdate(add_months(end, -12))


def _pct(numerator: float, denominator: float) -> float:
	return round(numerator / denominator * 100, 2) if denominator > 0 else 0.0


def _growth_pct(current: float, previous: float) -> float:
	if previous <= 0:
		return 0.0
	return round((current - previous) / previous * 100, 2)


def _finalize_salesperson_row(
	row: dict[str, Any],
	*,
	gp: float = 0.0,
	collection: float = 0.0,
	outstanding: float = 0.0,
	overdue: float = 0.0,
	sales_ly: float = 0.0,
) -> dict[str, Any]:
	total_sales = float(row.get("total_sales") or 0)
	gp_val = round(float(gp), 2)
	salesperson = resolve_salesperson_name(row.get("salesperson")) or row.get("salesperson") or "Unassigned"
	return {
		"salesperson": salesperson,
		"sales_person": salesperson,
		"total_sales": round(total_sales, 2),
		"invoice_count": int(row.get("invoice_count") or 0),
		"rank": row.get("rank"),
		"gp": gp_val,
		"gp_pct": _pct(gp_val, total_sales),
		"collection": round(float(collection), 2),
		"outstanding": round(float(outstanding), 2),
		"overdue": round(float(overdue), 2),
		"sales_ly": round(float(sales_ly), 2),
		"growth_pct": _growth_pct(total_sales, float(sales_ly)),
	}


def _ensure_salesperson_row_schema(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
	"""Guarantee identical keys on every row for all periods (MTD/YTD/custom range)."""
	ensured: list[dict[str, Any]] = []
	for row in rows:
		final = _finalize_salesperson_row(
			row,
			gp=row.get("gp", 0.0),
			collection=row.get("collection", 0.0),
			outstanding=row.get("outstanding", 0.0),
			overdue=row.get("overdue", 0.0),
			sales_ly=row.get("sales_ly", 0.0),
		)
		final["rank"] = row.get("rank")
		ensured.append(final)
	return ensured


def _norm_product_label(name: Optional[str]) -> str:
	return (name or "Unassigned").strip() or "Unassigned"


def _asp(total_sales: float, sold_qty: float) -> float:
	qty = float(sold_qty or 0)
	return round(total_sales / qty, 2) if qty > 0 else 0.0


def _finalize_product_row(row: dict[str, Any], *, sales_ly: float = 0.0) -> dict[str, Any]:
	label = _norm_product_label(row.get("label") or row.get("key"))
	total_sales = round(float(row.get("total_sales") or 0), 2)
	sold_qty = round(float(row.get("sold_qty") or 0), 2)
	gp_val = round(float(row.get("gp") or 0), 2)
	sales_ly_val = round(float(sales_ly), 2)
	return {
		"key": label,
		"label": label,
		"total_sales": total_sales,
		"sold_qty": sold_qty,
		"invoice_count": int(row.get("invoice_count") or 0),
		"rank": row.get("rank"),
		"gp": gp_val,
		"gp_pct": _pct(gp_val, total_sales),
		"customer_count": int(row.get("customer_count") or 0),
		"sales_ly": sales_ly_val,
		"growth_pct": _growth_pct(total_sales, sales_ly_val),
		"asp": _asp(total_sales, sold_qty),
	}


def _ensure_product_row_schema(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
	ensured: list[dict[str, Any]] = []
	for row in rows:
		final = _finalize_product_row(row, sales_ly=row.get("sales_ly", 0.0))
		final["rank"] = row.get("rank")
		ensured.append(final)
	return ensured


def _product_group_spec(group_by: str) -> tuple[str, str, str]:
	group_key = (group_by or "brand").lower()
	specs = {
		"brand": ("Brand", "brand", "COALESCE(sii.brand, 'Unassigned')"),
		"item": ("Item_Code", "item", "COALESCE(sii.item_code, 'Unassigned')"),
		"item_group": ("Sub_Group", "item_group", "COALESCE(i.item_group, 'Unassigned')"),
	}
	return specs.get(group_key, specs["brand"])


def _dashboard_division_sql(
	divisions: Optional[List[str]],
	cols: set[str],
) -> tuple[str, list[Any]]:
	if not divisions or "Division" not in cols:
		return "", []
	cleaned = [str(d).strip() for d in divisions if d is not None and str(d).strip()]
	if not cleaned:
		return "", []
	placeholders = ", ".join(["%s"] * len(cleaned))
	return f" AND COALESCE(`Division`, '') IN ({placeholders})", cleaned


def _dashboard_sub_group_sql(
	sub_groups: Optional[List[str]],
	cols: set[str],
) -> tuple[str, list[Any]]:
	if not sub_groups or "Sub_Group" not in cols:
		return "", []
	cleaned = [str(s).strip() for s in sub_groups if s is not None and str(s).strip()]
	if not cleaned:
		return "", []
	placeholders = ", ".join(["%s"] * len(cleaned))
	return f" AND COALESCE(`Sub_Group`, '') IN ({placeholders})", cleaned


def _product_metrics_from_dashboard(
	company: Optional[str],
	start: date,
	end: date,
	group_by: str,
	territories: Optional[List[str]] = None,
	divisions: Optional[List[str]] = None,
	sub_groups: Optional[List[str]] = None,
) -> dict[str, dict[str, Any]]:
	cols = _dashboard_columns()
	if not cols:
		return {}

	date_col = "Invoice_Date" if "Invoice_Date" in cols else "invoice_date"
	sales_col = "Net_Amount" if "Net_Amount" in cols else "net_amount"
	cogs_col = "COGS" if "COGS" in cols else "cogs"
	qty_col = "Sold_Qty" if "Sold_Qty" in cols else None
	col_name, _, _ = _product_group_spec(group_by)
	if col_name not in cols:
		return {}

	company_sql, company_params = _company_filter_dashboard(company, cols)
	terr_sql, terr_params = _dashboard_territory_sql(territories, cols)
	div_sql, div_params = _dashboard_division_sql(divisions, cols)
	sub_sql, sub_params = _dashboard_sub_group_sql(sub_groups, cols)
	qty_select = f"COALESCE(SUM(`{qty_col}`), 0) AS sold_qty," if qty_col and qty_col in cols else "0 AS sold_qty,"
	gp_select = (
		f"COALESCE(SUM(`{sales_col}`), 0) - COALESCE(SUM(`{cogs_col}`), 0) AS gp,"
		if cogs_col in cols
		else "0 AS gp,"
	)
	customer_select = (
		"COALESCE(COUNT(DISTINCT Customer), 0) AS customer_count,"
		if "Customer" in cols
		else "0 AS customer_count,"
	)

	rows = frappe.db.sql(
		f"""
		SELECT
			COALESCE(`{col_name}`, 'Unassigned') AS label,
			COALESCE(SUM(`{sales_col}`), 0) AS total_sales,
			{qty_select}
			COALESCE(COUNT(DISTINCT Invoice_No), 0) AS invoice_count,
			{gp_select}
			{customer_select}
			COALESCE(`{col_name}`, 'Unassigned') AS grp_key
		FROM `tabSalesDashBoard`
		WHERE `{date_col}` BETWEEN %s AND %s
		  {company_sql}
		  {terr_sql}
		  {div_sql}
		  {sub_sql}
		GROUP BY COALESCE(`{col_name}`, 'Unassigned')
		""",
		tuple([start, end, *company_params, *terr_params, *div_params, *sub_params]),
		as_dict=True,
	)

	result: dict[str, dict[str, Any]] = {}
	for row in rows:
		label = _norm_product_label(row.label)
		result[label] = {
			"label": label,
			"total_sales": float(row.total_sales or 0),
			"sold_qty": float(row.sold_qty or 0),
			"invoice_count": int(row.invoice_count or 0),
			"gp": float(row.gp or 0),
			"customer_count": int(row.customer_count or 0),
		}
	return result


def _product_metrics_from_sales_invoice(
	company: Optional[str],
	start: date,
	end: date,
	group_by: str,
	territories: Optional[List[str]] = None,
	divisions: Optional[List[str]] = None,
	sub_groups: Optional[List[str]] = None,
) -> dict[str, dict[str, Any]]:
	_, _, group_sql = _product_group_spec(group_by)
	company_sql = ""
	params: list[Any] = [start, end]
	if company:
		company_sql = " AND si.company = %s"
		params.append(company)
	terr_sql, terr_params = _si_territory_sql(territories)
	params.extend(terr_params)

	div_sql = ""
	if divisions:
		div_field = None
		for candidate in ("custom_division", "division"):
			if frappe.db.has_column("Sales Invoice", candidate):
				div_field = candidate
				break
		cleaned = [str(d).strip() for d in divisions if d is not None and str(d).strip()]
		if div_field and cleaned:
			placeholders = ", ".join(["%s"] * len(cleaned))
			div_sql = f" AND COALESCE(si.`{div_field}`, '') IN ({placeholders})"
			params.extend(cleaned)

	sub_sql = ""
	if sub_groups:
		cleaned = [str(s).strip() for s in sub_groups if s is not None and str(s).strip()]
		if cleaned:
			placeholders = ", ".join(["%s"] * len(cleaned))
			sub_sql = f" AND COALESCE(i.item_group, '') IN ({placeholders})"
			params.extend(cleaned)

	rows = frappe.db.sql(
		f"""
		SELECT
			{group_sql} AS label,
			COALESCE(SUM(sii.base_net_amount), 0) AS total_sales,
			COALESCE(SUM(sii.qty), 0) AS sold_qty,
			COUNT(DISTINCT si.name) AS invoice_count,
			COALESCE(SUM(
				GREATEST(
					sii.base_net_amount - (COALESCE(sii.incoming_rate, 0) * sii.qty),
					0
				)
			), 0) AS gp,
			COUNT(DISTINCT si.customer) AS customer_count
		FROM `tabSales Invoice` si
		INNER JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
		LEFT JOIN `tabItem` i ON i.name = sii.item_code
		WHERE si.docstatus = 1
		  AND si.posting_date BETWEEN %s AND %s
		  {company_sql}
		  {terr_sql}
		  {div_sql}
		  {sub_sql}
		GROUP BY {group_sql}
		""",
		tuple(params),
		as_dict=True,
	)

	result: dict[str, dict[str, Any]] = {}
	for row in rows:
		label = _norm_product_label(row.label)
		result[label] = {
			"label": label,
			"total_sales": float(row.total_sales or 0),
			"sold_qty": float(row.sold_qty or 0),
			"invoice_count": int(row.invoice_count or 0),
			"gp": float(row.gp or 0),
			"customer_count": int(row.customer_count or 0),
		}
	return result


def _merge_product_metric_pair(
	dash: dict[str, Any], si: dict[str, Any], *, company_rate: float = 0.0
) -> Optional[dict[str, Any]]:
	label = _norm_product_label(si.get("label") or dash.get("label"))
	d_sales = float(dash.get("total_sales") or 0)
	s_sales = float(si.get("total_sales") or 0)
	if d_sales <= 0 and s_sales <= 0:
		return None

	if s_sales > d_sales + 0.01:
		gp = float(si.get("gp") or 0)
		if d_sales > 0:
			gp = round(s_sales * min(float(dash.get("gp") or 0) / d_sales, 1.0), 2)
		elif company_rate > 0:
			gp = round(s_sales * company_rate, 2)
		return {
			"label": label,
			"total_sales": s_sales,
			"sold_qty": float(si.get("sold_qty") or 0),
			"invoice_count": int(si.get("invoice_count") or 0),
			"gp": gp,
			"customer_count": int(max(dash.get("customer_count") or 0, si.get("customer_count") or 0)),
		}

	source = dash if d_sales >= s_sales else si
	return {
		"label": label,
		"total_sales": float(source.get("total_sales") or 0),
		"sold_qty": float(source.get("sold_qty") or 0),
		"invoice_count": int(source.get("invoice_count") or 0),
		"gp": float(source.get("gp") or 0),
		"customer_count": int(source.get("customer_count") or 0),
	}


def _merged_product_rows(
	company: Optional[str],
	start: date,
	end: date,
	group_by: str,
	limit: int,
	territories: Optional[List[str]] = None,
	divisions: Optional[List[str]] = None,
	sub_groups: Optional[List[str]] = None,
) -> list[dict[str, Any]]:
	dashboard = _product_metrics_from_dashboard(
		company, start, end, group_by, territories, divisions=divisions, sub_groups=sub_groups
	)
	si = _product_metrics_from_sales_invoice(
		company, start, end, group_by, territories, divisions=divisions, sub_groups=sub_groups
	)
	company_rate = _company_dashboard_gp_rate(company, start, end) if dashboard else 0.0

	merged: list[dict[str, Any]] = []
	for label in set(dashboard) | set(si):
		row = _merge_product_metric_pair(dashboard.get(label, {}), si.get(label, {}), company_rate=company_rate)
		if row:
			merged.append(row)

	merged.sort(key=lambda r: r["total_sales"], reverse=True)
	return merged[: int(limit)]


def _product_sales_ly_map(
	company: Optional[str],
	ly_start: date,
	ly_end: date,
	group_by: str,
	territories: Optional[List[str]] = None,
	divisions: Optional[List[str]] = None,
	sub_groups: Optional[List[str]] = None,
) -> dict[str, float]:
	dashboard = _product_metrics_from_dashboard(
		company, ly_start, ly_end, group_by, territories, divisions=divisions, sub_groups=sub_groups
	)
	si = _product_metrics_from_sales_invoice(
		company, ly_start, ly_end, group_by, territories, divisions=divisions, sub_groups=sub_groups
	)
	company_rate = _company_dashboard_gp_rate(company, ly_start, ly_end) if dashboard else 0.0

	out: dict[str, float] = {}
	for label in set(dashboard) | set(si):
		row = _merge_product_metric_pair(dashboard.get(label, {}), si.get(label, {}), company_rate=company_rate)
		if row:
			out[label] = float(row.get("total_sales") or 0)
	return out


def get_salesperson_ranking(
	company: Optional[str] = None,
	period: Optional[str] = None,
	from_date: Optional[str] = None,
	to_date: Optional[str] = None,
	limit: int = 20,
	territories: Optional[List[str]] = None,
) -> dict[str, Any]:
	start, end = _period_bounds(period, from_date, to_date)
	rows = _merged_salesperson_rows(company, start, end, limit, territories)

	rows = _enrich_salesperson_rows(
		rows,
		company=company,
		start=start,
		end=end,
	)

	for idx, row in enumerate(rows, start=1):
		row["rank"] = idx

	rows = _ensure_salesperson_row_schema(rows)

	return {
		"period": {"from_date": str(start), "to_date": str(end)},
		"rows": rows,
	}


def _merged_salesperson_rows(
	company: Optional[str],
	start: date,
	end: date,
	limit: int,
	territories: Optional[List[str]] = None,
) -> list[dict[str, Any]]:
	"""Merge SalesDashBoard + Sales Invoice totals — SI wins when dashboard is incomplete."""
	merge_cap = max(int(limit) * 10, 200)
	dashboard_rows = _salesperson_from_dashboard(company, start, end, merge_cap, territories)
	si_rows = _salesperson_from_sales_invoice(company, start, end, merge_cap, territories)

	dashboard_by_key: dict[str, dict[str, Any]] = {}
	for row in dashboard_rows:
		dashboard_by_key[_norm_salesperson(row["salesperson"])] = row

	si_by_key: dict[str, dict[str, Any]] = {}
	for row in si_rows:
		si_by_key[_norm_salesperson(row["salesperson"])] = row

	merged: list[dict[str, Any]] = []
	for key in set(dashboard_by_key) | set(si_by_key):
		dash = dashboard_by_key.get(key, {})
		si = si_by_key.get(key, {})
		dash_sales = float(dash.get("total_sales") or 0)
		si_sales = float(si.get("total_sales") or 0)
		display_name = si.get("salesperson") or dash.get("salesperson") or key

		if si_sales > dash_sales + 0.01:
			merged.append(
				{
					"salesperson": display_name,
					"total_sales": round(si_sales, 2),
					"invoice_count": int(si.get("invoice_count") or 0),
					"sales_source": "sales_invoice",
				}
			)
		elif dash_sales > 0 or si_sales > 0:
			merged.append(
				{
					"salesperson": display_name,
					"total_sales": round(max(dash_sales, si_sales), 2),
					"invoice_count": int(
						dash.get("invoice_count") if dash_sales >= si_sales else si.get("invoice_count") or 0
					),
					"sales_source": "dashboard" if dash_sales >= si_sales and dash_sales > 0 else "sales_invoice",
				}
			)

	merged.sort(key=lambda r: r["total_sales"], reverse=True)
	return merged[: int(limit)]


def _merged_sales_ly_map(
	company: Optional[str], ly_start: date, ly_end: date
) -> dict[str, float]:
	"""Last-year sales totals — max(dashboard, sales invoice) per salesperson."""
	dashboard = _sales_totals_by_salesperson_dashboard(company, ly_start, ly_end)
	si = _sales_totals_by_salesperson_sales_invoice(company, ly_start, ly_end)
	keys = set(dashboard) | set(si)
	return {key: max(float(dashboard.get(key, 0)), float(si.get(key, 0))) for key in keys}


def _enrich_salesperson_rows(
	rows: list[dict[str, Any]],
	company: Optional[str],
	start: date,
	end: date,
) -> list[dict[str, Any]]:
	if not rows:
		return rows

	ly_start, ly_end = _ly_period(start, end)
	has_dashboard = bool(_dashboard_columns())

	if has_dashboard:
		collection_map = _collection_by_salesperson_dashboard(company, start, end)
		ar_map = _ar_by_salesperson_dashboard(company)
	else:
		collection_map = _collection_by_salesperson(company, start, end)
		ar_map = _ar_by_salesperson(company)

	sales_ly_map = _merged_sales_ly_map(company, ly_start, ly_end)
	gp_map = (
		_gp_by_salesperson_invoice_merge(company, start, end)
		if has_dashboard
		else _gp_by_salesperson_sales_invoice(company, start, end)
	)

	enriched: list[dict[str, Any]] = []
	for row in rows:
		sp = row.get("salesperson") or "Unassigned"
		ar = _map_get_ar(ar_map, sp)
		gp = _map_get_float(gp_map, sp)

		enriched.append(
			_finalize_salesperson_row(
				row,
				gp=gp,
				collection=_map_get_float(collection_map, sp),
				outstanding=float(ar.get("outstanding", 0.0)),
				overdue=float(ar.get("overdue", 0.0)),
				sales_ly=_map_get_float(sales_ly_map, sp),
			)
		)
	return enriched


def _salesperson_from_dashboard(
	company: Optional[str],
	start: date,
	end: date,
	limit: int,
	territories: Optional[List[str]] = None,
) -> list[dict[str, Any]]:
	cols = _dashboard_columns()
	if not cols:
		return []

	date_col = "Invoice_Date" if "Invoice_Date" in cols else "invoice_date"
	sales_col = "Net_Amount" if "Net_Amount" in cols else "net_amount"
	person_col = "Sales_Person" if "Sales_Person" in cols else None
	if not person_col:
		return []

	company_sql, company_params = _company_filter_dashboard(company, cols)
	terr_sql, terr_params = _dashboard_territory_sql(territories, cols)

	rows = frappe.db.sql(
		f"""
		SELECT
			COALESCE(`{person_col}`, 'Unassigned') AS salesperson,
			COALESCE(SUM(`{sales_col}`), 0) AS total_sales,
			COALESCE(COUNT(DISTINCT Invoice_No), 0) AS invoice_count
		FROM `tabSalesDashBoard`
		WHERE `{date_col}` BETWEEN %s AND %s
		  {company_sql}
		  {terr_sql}
		GROUP BY COALESCE(`{person_col}`, 'Unassigned')
		ORDER BY total_sales DESC
		LIMIT %s
		""",
		tuple([start, end, *company_params, *terr_params, int(limit)]),
		as_dict=True,
	)

	return [
		{
			"salesperson": row.salesperson,
			"total_sales": round(float(row.total_sales or 0), 2),
			"invoice_count": int(row.invoice_count or 0),
		}
		for row in rows
	]


def _salesperson_from_sales_invoice(
	company: Optional[str],
	start: date,
	end: date,
	limit: int,
	territories: Optional[List[str]] = None,
) -> list[dict[str, Any]]:
	company_sql = ""
	params: list[Any] = [start, end]
	if company:
		company_sql = " AND si.company = %s"
		params.append(company)
	terr_sql, terr_params = _si_territory_sql(territories)
	params.extend(terr_params)

	if frappe.db.table_exists("Sales Team"):
		rows = frappe.db.sql(
			f"""
			SELECT
				COALESCE(st.sales_person, 'Unassigned') AS salesperson,
				COALESCE(SUM(st.allocated_amount), 0) AS total_sales,
				COUNT(DISTINCT si.name) AS invoice_count
			FROM `tabSales Invoice` si
			INNER JOIN `tabSales Team` st ON st.parent = si.name AND st.parenttype = 'Sales Invoice'
			WHERE si.docstatus = 1
			  AND si.posting_date BETWEEN %s AND %s
			  {company_sql}
			  {terr_sql}
			GROUP BY COALESCE(st.sales_person, 'Unassigned')
			ORDER BY total_sales DESC
			LIMIT %s
			""",
			tuple([*params, int(limit)]),
			as_dict=True,
		)
		if rows:
			return [
				{
					"salesperson": row.salesperson,
					"total_sales": round(float(row.total_sales or 0), 2),
					"invoice_count": int(row.invoice_count or 0),
				}
				for row in rows
			]

	rows = frappe.db.sql(
		f"""
		SELECT
			COALESCE(si.owner, 'Unassigned') AS salesperson,
			COALESCE(SUM(si.base_net_total), 0) AS total_sales,
			COUNT(si.name) AS invoice_count
		FROM `tabSales Invoice` si
		WHERE si.docstatus = 1
		  AND si.posting_date BETWEEN %s AND %s
		  {company_sql}
		  {terr_sql}
		GROUP BY COALESCE(si.owner, 'Unassigned')
		ORDER BY total_sales DESC
		LIMIT %s
		""",
		tuple([*params, int(limit)]),
		as_dict=True,
	)

	return [
		{
			"salesperson": row.salesperson,
			"total_sales": round(float(row.total_sales or 0), 2),
			"invoice_count": int(row.invoice_count or 0),
		}
		for row in rows
	]


def _gp_by_salesperson_dashboard(
	company: Optional[str], start: date, end: date
) -> dict[str, float]:
	cols = _dashboard_columns()
	if not cols:
		return {}

	date_col = "Invoice_Date" if "Invoice_Date" in cols else "invoice_date"
	sales_col = "Net_Amount" if "Net_Amount" in cols else "net_amount"
	cogs_col = "COGS" if "COGS" in cols else "cogs"
	person_col = "Sales_Person" if "Sales_Person" in cols else None
	if not person_col or cogs_col not in cols:
		return {}

	company_sql, company_params = _company_filter_dashboard(company, cols)
	rows = frappe.db.sql(
		f"""
		SELECT
			COALESCE(`{person_col}`, 'Unassigned') AS salesperson,
			COALESCE(SUM(`{sales_col}`), 0) - COALESCE(SUM(`{cogs_col}`), 0) AS gp
		FROM `tabSalesDashBoard`
		WHERE `{date_col}` BETWEEN %s AND %s
		  {company_sql}
		GROUP BY COALESCE(`{person_col}`, 'Unassigned')
		""",
		tuple([start, end, *company_params]),
		as_dict=True,
	)
	return {_norm_salesperson(row.salesperson): float(row.gp or 0) for row in rows}


def _company_dashboard_gp_rate(company: Optional[str], start: date, end: date) -> float:
	"""Company-wide dashboard GP margin — fallback for invoices missing from SalesDashBoard."""
	cols = _dashboard_columns()
	if not cols:
		return 0.0

	date_col = "Invoice_Date" if "Invoice_Date" in cols else "invoice_date"
	sales_col = "Net_Amount" if "Net_Amount" in cols else "net_amount"
	cogs_col = "COGS" if "COGS" in cols else "cogs"
	if cogs_col not in cols:
		return 0.0

	company_sql, company_params = _company_filter_dashboard(company, cols)
	row = frappe.db.sql(
		f"""
		SELECT
			COALESCE(SUM(`{sales_col}`), 0) AS total_sales,
			COALESCE(SUM(`{sales_col}`), 0) - COALESCE(SUM(`{cogs_col}`), 0) AS gp
		FROM `tabSalesDashBoard`
		WHERE `{date_col}` BETWEEN %s AND %s
		  {company_sql}
		""",
		tuple([start, end, *company_params]),
		as_dict=True,
	)
	if not row:
		return 0.0
	total_sales = float(row[0].total_sales or 0)
	gp = float(row[0].gp or 0)
	if total_sales <= 0:
		return 0.0
	return min(max(gp / total_sales, 0.0), 1.0)


def _gp_by_salesperson_invoice_merge(
	company: Optional[str], start: date, end: date
) -> dict[str, float]:
	"""GP per salesperson: dashboard invoice GP when present, else company GP rate on SI allocation."""
	cols = _dashboard_columns()
	if not cols or not frappe.db.table_exists("Sales Team"):
		return {}

	sales_col = "Net_Amount" if "Net_Amount" in cols else "net_amount"
	cogs_col = "COGS" if "COGS" in cols else "cogs"
	if cogs_col not in cols or sales_col not in cols:
		return _gp_by_salesperson_dashboard(company, start, end)

	company_rate = _company_dashboard_gp_rate(company, start, end)
	company_sql = ""
	params: list[Any] = [start, end]
	if company:
		company_sql = " AND si.company = %s"
		params.append(company)

	rows = frappe.db.sql(
		f"""
		SELECT
			COALESCE(st.sales_person, 'Unassigned') AS salesperson,
			COALESCE(SUM(
				CASE
					WHEN dash.invoice_gp IS NOT NULL THEN
						dash.invoice_gp * st.allocated_percentage / 100.0
					ELSE
						st.allocated_amount * %s
				END
			), 0) AS gp
		FROM `tabSales Invoice` si
		INNER JOIN `tabSales Team` st ON st.parent = si.name AND st.parenttype = 'Sales Invoice'
		LEFT JOIN (
			SELECT
				Invoice_No,
				SUM(`{sales_col}`) - SUM(`{cogs_col}`) AS invoice_gp
			FROM `tabSalesDashBoard`
			WHERE Invoice_No IS NOT NULL AND Invoice_No != ''
			GROUP BY Invoice_No
		) dash ON dash.Invoice_No = si.name
		WHERE si.docstatus = 1
		  AND si.posting_date BETWEEN %s AND %s
		  {company_sql}
		GROUP BY COALESCE(st.sales_person, 'Unassigned')
		""",
		tuple([company_rate, *params]),
		as_dict=True,
	)
	return {_norm_salesperson(row.salesperson): float(row.gp or 0) for row in rows}


def _dashboard_invoice_person_subquery() -> str:
	return """
		(
			SELECT
				Invoice_No,
				MAX(Sales_Person) AS Sales_Person
			FROM `tabSalesDashBoard`
			WHERE Invoice_No IS NOT NULL AND Invoice_No != ''
			GROUP BY Invoice_No
		) d
	"""


def _collection_by_salesperson_dashboard(
	company: Optional[str], start: date, end: date
) -> dict[str, float]:
	if not _dashboard_columns():
		return {}

	rows = frappe.db.sql(
		f"""
		SELECT
			COALESCE(d.Sales_Person, 'Unassigned') AS salesperson,
			COALESCE(SUM(per.allocated_amount), 0) AS collection
		FROM `tabPayment Entry` pe
		INNER JOIN `tabPayment Entry Reference` per ON per.parent = pe.name
			AND per.reference_doctype = 'Sales Invoice'
		INNER JOIN {_dashboard_invoice_person_subquery()} ON d.Invoice_No = per.reference_name
		WHERE pe.docstatus = 1
		  AND pe.payment_type = 'Receive'
		  AND pe.posting_date BETWEEN %s AND %s
		GROUP BY COALESCE(d.Sales_Person, 'Unassigned')
		""",
		(start, end),
		as_dict=True,
	)
	return {_norm_salesperson(row.salesperson): float(row.collection or 0) for row in rows}


def _ar_by_salesperson_dashboard(company: Optional[str]) -> dict[str, dict[str, float]]:
	if not _dashboard_columns():
		return {}

	company_sql = ""
	params: list[Any] = []
	if company:
		company_sql = " AND si.company = %s"
		params.append(company)

	rows = frappe.db.sql(
		f"""
		SELECT
			COALESCE(d.Sales_Person, 'Unassigned') AS salesperson,
			COALESCE(SUM(si.outstanding_amount), 0) AS outstanding,
			COALESCE(SUM(
				CASE WHEN si.due_date < CURDATE() THEN si.outstanding_amount ELSE 0 END
			), 0) AS overdue
		FROM `tabSales Invoice` si
		INNER JOIN {_dashboard_invoice_person_subquery()} ON d.Invoice_No = si.name
		WHERE si.docstatus = 1
		  AND si.outstanding_amount > 0
		  {company_sql}
		GROUP BY COALESCE(d.Sales_Person, 'Unassigned')
		""",
		tuple(params),
		as_dict=True,
	)
	return {
		_norm_salesperson(row.salesperson): {
			"outstanding": float(row.outstanding or 0),
			"overdue": float(row.overdue or 0),
		}
		for row in rows
	}


def _sales_totals_by_salesperson_dashboard(
	company: Optional[str], start: date, end: date
) -> dict[str, float]:
	cols = _dashboard_columns()
	if not cols:
		return {}

	date_col = "Invoice_Date" if "Invoice_Date" in cols else "invoice_date"
	sales_col = "Net_Amount" if "Net_Amount" in cols else "net_amount"
	person_col = "Sales_Person" if "Sales_Person" in cols else None
	if not person_col:
		return {}

	company_sql, company_params = _company_filter_dashboard(company, cols)
	rows = frappe.db.sql(
		f"""
		SELECT
			COALESCE(`{person_col}`, 'Unassigned') AS salesperson,
			COALESCE(SUM(`{sales_col}`), 0) AS total_sales
		FROM `tabSalesDashBoard`
		WHERE `{date_col}` BETWEEN %s AND %s
		  {company_sql}
		GROUP BY COALESCE(`{person_col}`, 'Unassigned')
		""",
		tuple([start, end, *company_params]),
		as_dict=True,
	)
	return {_norm_salesperson(row.salesperson): float(row.total_sales or 0) for row in rows}


def _gp_by_salesperson_sales_invoice(
	company: Optional[str], start: date, end: date
) -> dict[str, float]:
	company_sql = ""
	params: list[Any] = [start, end]
	if company:
		company_sql = " AND si.company = %s"
		params.append(company)

	if frappe.db.table_exists("Sales Team"):
		rows = frappe.db.sql(
			f"""
			SELECT
				COALESCE(st.sales_person, 'Unassigned') AS salesperson,
				COALESCE(SUM(
					GREATEST(
						sii.base_net_amount - (COALESCE(sii.incoming_rate, 0) * sii.qty),
						0
					) * st.allocated_percentage / 100.0
				), 0) AS gp
			FROM `tabSales Invoice` si
			INNER JOIN `tabSales Team` st ON st.parent = si.name AND st.parenttype = 'Sales Invoice'
			INNER JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
			WHERE si.docstatus = 1
			  AND si.posting_date BETWEEN %s AND %s
			  {company_sql}
			GROUP BY COALESCE(st.sales_person, 'Unassigned')
			""",
			tuple(params),
			as_dict=True,
		)
		if rows:
			return {_norm_salesperson(row.salesperson): float(row.gp or 0) for row in rows}

	return {}


def _sales_totals_by_salesperson_sales_invoice(
	company: Optional[str], start: date, end: date
) -> dict[str, float]:
	company_sql = ""
	params: list[Any] = [start, end]
	if company:
		company_sql = " AND si.company = %s"
		params.append(company)

	if frappe.db.table_exists("Sales Team"):
		rows = frappe.db.sql(
			f"""
			SELECT
				COALESCE(st.sales_person, 'Unassigned') AS salesperson,
				COALESCE(SUM(st.allocated_amount), 0) AS total_sales
			FROM `tabSales Invoice` si
			INNER JOIN `tabSales Team` st ON st.parent = si.name AND st.parenttype = 'Sales Invoice'
			WHERE si.docstatus = 1
			  AND si.posting_date BETWEEN %s AND %s
			  {company_sql}
			GROUP BY COALESCE(st.sales_person, 'Unassigned')
			""",
			tuple(params),
			as_dict=True,
		)
		if rows:
			return {_norm_salesperson(row.salesperson): float(row.total_sales or 0) for row in rows}

	rows = frappe.db.sql(
		f"""
		SELECT
			COALESCE(si.owner, 'Unassigned') AS salesperson,
			COALESCE(SUM(si.base_net_total), 0) AS total_sales
		FROM `tabSales Invoice` si
		WHERE si.docstatus = 1
		  AND si.posting_date BETWEEN %s AND %s
		  {company_sql}
		GROUP BY COALESCE(si.owner, 'Unassigned')
		""",
		tuple([*params]),
		as_dict=True,
	)
	return {_norm_salesperson(row.salesperson): float(row.total_sales or 0) for row in rows}


def _collection_by_salesperson(
	company: Optional[str], start: date, end: date
) -> dict[str, float]:
	company_sql = ""
	params: list[Any] = [start, end]
	if company:
		company_sql = " AND pe.company = %s"
		params.append(company)

	if not frappe.db.table_exists("Sales Team"):
		return {}

	rows = frappe.db.sql(
		f"""
		SELECT
			COALESCE(st.sales_person, 'Unassigned') AS salesperson,
			COALESCE(SUM(per.allocated_amount), 0) AS collection
		FROM `tabPayment Entry` pe
		INNER JOIN `tabPayment Entry Reference` per ON per.parent = pe.name
		INNER JOIN `tabSales Invoice` si ON si.name = per.reference_name
			AND per.reference_doctype = 'Sales Invoice'
		INNER JOIN `tabSales Team` st ON st.parent = si.name AND st.parenttype = 'Sales Invoice'
		WHERE pe.docstatus = 1
		  AND pe.payment_type = 'Receive'
		  AND pe.posting_date BETWEEN %s AND %s
		  {company_sql}
		GROUP BY COALESCE(st.sales_person, 'Unassigned')
		""",
		tuple(params),
		as_dict=True,
	)
	return {_norm_salesperson(row.salesperson): float(row.collection or 0) for row in rows}


def _ar_by_salesperson(company: Optional[str]) -> dict[str, dict[str, float]]:
	company_sql = ""
	params: list[Any] = []
	if company:
		company_sql = " AND si.company = %s"
		params.append(company)

	if frappe.db.table_exists("Sales Team"):
		rows = frappe.db.sql(
			f"""
			SELECT
				COALESCE(st.sales_person, 'Unassigned') AS salesperson,
				COALESCE(SUM(si.outstanding_amount), 0) AS outstanding,
				COALESCE(SUM(
					CASE WHEN si.due_date < CURDATE() THEN si.outstanding_amount ELSE 0 END
				), 0) AS overdue
			FROM `tabSales Invoice` si
			INNER JOIN `tabSales Team` st ON st.parent = si.name AND st.parenttype = 'Sales Invoice'
			WHERE si.docstatus = 1
			  AND si.outstanding_amount > 0
			  {company_sql}
			GROUP BY COALESCE(st.sales_person, 'Unassigned')
			""",
			tuple(params),
			as_dict=True,
		)
		if rows:
			return {
				_norm_salesperson(row.salesperson): {
					"outstanding": float(row.outstanding or 0),
					"overdue": float(row.overdue or 0),
				}
				for row in rows
			}

	rows = frappe.db.sql(
		f"""
		SELECT
			COALESCE(si.owner, 'Unassigned') AS salesperson,
			COALESCE(SUM(si.outstanding_amount), 0) AS outstanding,
			COALESCE(SUM(
				CASE WHEN si.due_date < CURDATE() THEN si.outstanding_amount ELSE 0 END
			), 0) AS overdue
		FROM `tabSales Invoice` si
		WHERE si.docstatus = 1
		  AND si.outstanding_amount > 0
		  {company_sql}
		GROUP BY COALESCE(si.owner, 'Unassigned')
		""",
		tuple(params),
		as_dict=True,
	)
	return {
		_norm_salesperson(row.salesperson): {
			"outstanding": float(row.outstanding or 0),
			"overdue": float(row.overdue or 0),
		}
		for row in rows
	}


def _item_sales_from_dashboard(
	company: Optional[str],
	item_code: str,
	start: date,
	end: date,
	*,
	brand: Optional[str] = None,
	territories: Optional[List[str]] = None,
) -> dict[str, float]:
	cols = _dashboard_columns()
	if not cols or "Item_Code" not in cols:
		return {"sold_qty": 0.0, "total_sales": 0.0}

	date_col = "Invoice_Date" if "Invoice_Date" in cols else "invoice_date"
	sales_col = "Net_Amount" if "Net_Amount" in cols else "net_amount"
	qty_col = "Sold_Qty" if "Sold_Qty" in cols else None
	if not qty_col:
		return {"sold_qty": 0.0, "total_sales": 0.0}

	company_sql, company_params = _company_filter_dashboard(company, cols)
	terr_sql, terr_params = _dashboard_territory_sql(territories, cols)
	brand_sql = ""
	brand_params: list[Any] = []
	if brand is not None and str(brand).strip() and "Brand" in cols:
		brand_sql = " AND COALESCE(`Brand`, 'Unassigned') = %s"
		brand_params = [brand.strip()]
	status_sql = ""
	if "Doc_Status" in cols:
		status_sql = " AND (`Doc_Status` = 1 OR `Doc_Status` IS NULL)"

	params: list[Any] = [item_code, start, end, *company_params, *terr_params, *brand_params]
	row = frappe.db.sql(
		f"""
		SELECT
			COALESCE(SUM(`{qty_col}`), 0) AS sold_qty,
			COALESCE(SUM(`{sales_col}`), 0) AS total_sales
		FROM `tabSalesDashBoard`
		WHERE `Item_Code` = %s
		  AND `{date_col}` BETWEEN %s AND %s
		  {company_sql}
		  {terr_sql}
		  {brand_sql}
		  {status_sql}
		""",
		tuple(params),
		as_dict=True,
	)
	if not row:
		return {"sold_qty": 0.0, "total_sales": 0.0}
	return {
		"sold_qty": float(row[0].sold_qty or 0),
		"total_sales": float(row[0].total_sales or 0),
	}


def _item_sales_from_sales_invoice(
	company: Optional[str],
	item_code: str,
	start: date,
	end: date,
	*,
	brand: Optional[str] = None,
	territories: Optional[List[str]] = None,
) -> dict[str, float]:
	company_sql = ""
	params: list[Any] = [item_code, start, end]
	if company:
		company_sql = " AND si.company = %s"
		params.append(company)
	terr_sql, terr_params = _si_territory_sql(territories)
	params.extend(terr_params)
	brand_sql = ""
	if brand is not None and str(brand).strip():
		brand_sql = " AND COALESCE(NULLIF(i.brand, ''), 'No Brand') = %s"
		params.append(brand.strip())

	row = frappe.db.sql(
		f"""
		SELECT
			COALESCE(SUM(sii.qty), 0) AS sold_qty,
			COALESCE(SUM(sii.base_net_amount), 0) AS total_sales
		FROM `tabSales Invoice` si
		INNER JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
		LEFT JOIN `tabItem` i ON i.name = sii.item_code
		WHERE si.docstatus = 1
		  AND sii.item_code = %s
		  AND si.posting_date BETWEEN %s AND %s
		  {company_sql}
		  {terr_sql}
		  {brand_sql}
		""",
		tuple(params),
		as_dict=True,
	)
	if not row:
		return {"sold_qty": 0.0, "total_sales": 0.0}
	return {
		"sold_qty": float(row[0].sold_qty or 0),
		"total_sales": float(row[0].total_sales or 0),
	}


def get_item_sales_metrics(
	company: Optional[str],
	item_code: str,
	start: date,
	end: date,
	*,
	brand: Optional[str] = None,
	territories: Optional[List[str]] = None,
) -> dict[str, float]:
	"""Sold qty and net sales for one item (SalesDashBoard + SI merge, same as rankings)."""
	item_code = (item_code or "").strip()
	if not item_code:
		return {"sold_qty": 0.0, "total_sales": 0.0}

	dash = {
		"label": item_code,
		**_item_sales_from_dashboard(
			company, item_code, start, end, brand=brand, territories=territories
		),
	}
	si = {
		"label": item_code,
		**_item_sales_from_sales_invoice(
			company, item_code, start, end, brand=brand, territories=territories
		),
	}
	merged = _merge_product_metric_pair(dash, si)
	if not merged:
		return {"sold_qty": 0.0, "total_sales": 0.0}
	return {
		"sold_qty": float(merged.get("sold_qty") or 0),
		"total_sales": float(merged.get("total_sales") or 0),
	}


def get_item_product_performance(
	company: Optional[str],
	item_code: str,
	period: Optional[str] = None,
	from_date: Optional[str] = None,
	to_date: Optional[str] = None,
	*,
	brand: Optional[str] = None,
	territories: Optional[List[str]] = None,
) -> dict[str, Any]:
	"""Mobile days-of-supply payload: one row with qty (sold), sales, asp."""
	start, end = _period_bounds(period, from_date, to_date)
	item_code = (item_code or "").strip()
	metrics = get_item_sales_metrics(
		company, item_code, start, end, brand=brand, territories=territories
	)
	sold_qty = round(metrics["sold_qty"], 2)
	total_sales = round(metrics["total_sales"], 2)
	return {
		"level": "item",
		"period": {"from_date": str(start), "to_date": str(end)},
		"rows": [
			{
				"item_code": item_code,
				"qty": sold_qty,
				"sales": total_sales,
				"asp": _asp(total_sales, sold_qty),
			}
		],
	}


def get_item_sales_qty(
	company: Optional[str],
	item_code: str,
	period: Optional[str] = None,
	from_date: Optional[str] = None,
	to_date: Optional[str] = None,
	*,
	brand: Optional[str] = None,
	territory: Optional[str] = None,
	territories: Optional[List[str]] = None,
) -> dict[str, Any]:
	"""Sold qty and sales value for one item in a date range (optional territory filter)."""
	start, end = _period_bounds(period, from_date, to_date)
	item_code = (item_code or "").strip()
	terr_list: Optional[List[str]] = None
	if territory:
		terr_list = [territory.strip()]
	elif territories:
		if isinstance(territories, str):
			terr_list = [t.strip() for t in territories.split(",") if t.strip()]
		else:
			terr_list = list(territories)

	metrics = get_item_sales_metrics(
		company, item_code, start, end, brand=brand, territories=terr_list
	)
	sold_qty = round(metrics["sold_qty"], 2)
	total_sales = round(metrics["total_sales"], 2)
	out: dict[str, Any] = {
		"item_code": item_code,
		"from_date": str(start),
		"to_date": str(end),
		"qty_sold": sold_qty,
		"sales_value": total_sales,
		# Mobile parser aliases (itemSalesQty.ts)
		"qty": sold_qty,
		"sales_qty": sold_qty,
		"quantity_sold": sold_qty,
	}
	if territory:
		out["territory"] = territory.strip()
	return out


def get_product_ranking(
	company: Optional[str] = None,
	group_by: str = "brand",
	period: Optional[str] = None,
	from_date: Optional[str] = None,
	to_date: Optional[str] = None,
	limit: int = 20,
	territories: Optional[List[str]] = None,
	division: Any = None,
	sub_group: Any = None,
) -> dict[str, Any]:
	start, end = _period_bounds(period, from_date, to_date)
	ly_start, ly_end = _ly_period(start, end)
	group_key = (group_by or "brand").lower()
	if group_key not in ("item", "item_group", "brand"):
		group_key = "brand"

	divisions: Optional[List[str]] = None
	if division is not None:
		if isinstance(division, (list, tuple)):
			divisions = [str(d).strip() for d in division if d is not None and str(d).strip()]
		elif str(division).strip():
			divisions = [str(division).strip()]

	sub_groups: Optional[List[str]] = None
	if sub_group is not None:
		if isinstance(sub_group, (list, tuple)):
			sub_groups = [str(s).strip() for s in sub_group if s is not None and str(s).strip()]
		elif str(sub_group).strip():
			sub_groups = [str(sub_group).strip()]

	if sub_groups:
		from erp_analysis.services.analytics_sales import _coalesce_dashboard_filter_keys

		coalesced = _coalesce_dashboard_filter_keys(
			{"division": divisions or [], "sub_group": sub_groups}
		)
		sub_groups = coalesced.get("sub_group") or sub_groups

	rows = _merged_product_rows(
		company, start, end, group_key, limit, territories, divisions=divisions, sub_groups=sub_groups
	)
	sales_ly_map = _product_sales_ly_map(
		company, ly_start, ly_end, group_key, territories, divisions=divisions, sub_groups=sub_groups
	)

	enriched: list[dict[str, Any]] = []
	for row in rows:
		label = _norm_product_label(row.get("label"))
		enriched.append(_finalize_product_row(row, sales_ly=sales_ly_map.get(label, 0.0)))

	for idx, row in enumerate(enriched, start=1):
		row["rank"] = idx

	rows = _ensure_product_row_schema(enriched)

	return {
		"group_by": group_key,
		"period": {"from_date": str(start), "to_date": str(end)},
		"rows": rows,
	}


def get_salesperson_invoices(
	company: Optional[str] = None,
	salesperson: Optional[str] = None,
	from_date: Optional[str] = None,
	to_date: Optional[str] = None,
	limit: int = 50,
	offset: int = 0,
	territories: Optional[List[str]] = None,
) -> dict[str, Any]:
	"""Invoice drill-down for a salesperson — mobile-safe alternative to frappe.client.get_list."""
	start, end = _period_bounds(None, from_date, to_date)
	salesperson = resolve_salesperson_name(salesperson) or salesperson
	if not salesperson:
		return {
			"salesperson": "",
			"period": {"from_date": str(start), "to_date": str(end)},
			"rows": [],
			"pagination": {"limit": int(limit), "offset": int(offset), "count": 0},
		}

	company_sql = ""
	params: list[Any] = [salesperson, start, end]
	if company:
		company_sql = " AND si.company = %s"
		params.append(company)
	terr_sql, terr_params = _si_territory_sql(territories)
	params.extend(terr_params)

	rows = frappe.db.sql(
		f"""
		SELECT
			si.name AS invoice_no,
			si.posting_date,
			si.customer,
			si.customer_name,
			COALESCE(st.allocated_amount, si.base_net_total) AS net_amount,
			si.outstanding_amount,
			si.status
		FROM `tabSales Invoice` si
		INNER JOIN `tabSales Team` st ON st.parent = si.name AND st.parenttype = 'Sales Invoice'
		WHERE si.docstatus = 1
		  AND st.sales_person = %s
		  AND si.posting_date BETWEEN %s AND %s
		  {company_sql}
		  {terr_sql}
		ORDER BY si.posting_date DESC, si.name DESC
		LIMIT %s OFFSET %s
		""",
		tuple([*params, int(limit), int(offset)]),
		as_dict=True,
	)

	formatted = [
		{
			"invoice_no": row.invoice_no,
			"posting_date": str(row.posting_date) if row.posting_date else None,
			"customer": row.customer,
			"customer_name": row.customer_name or row.customer,
			"net_amount": round(float(row.net_amount or 0), 2),
			"outstanding_amount": round(float(row.outstanding_amount or 0), 2),
			"status": row.status or "",
		}
		for row in rows
	]

	return {
		"salesperson": salesperson,
		"period": {"from_date": str(start), "to_date": str(end)},
		"rows": formatted,
		"pagination": {"limit": int(limit), "offset": int(offset), "count": len(formatted)},
	}
