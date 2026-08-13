# apps/erp_analysis/erp_analysis/sales_kpis.py

import json
import frappe
from frappe.utils import getdate, nowdate, get_first_day, get_last_day, add_years
import datetime as dt
from calendar import monthrange
from typing import Any, Dict, List, Optional, Tuple


# -----------------------
# Small, local helpers
# -----------------------

# Copyright (c) 2025
# SPDX-License-Identifier: MIT



"""Sales & Finance KPIs API with resilient date-column detection."""

import datetime as dt
from calendar import monthrange
from typing import Any, Dict, List, Optional, Tuple

import frappe
from frappe.utils import getdate, nowdate


# ------------------------
# Utilities
# ------------------------

def _parse_date(d: Optional[str]) -> dt.date:
    return getdate(d) if d else getdate(nowdate())


def _month_start(d: dt.date) -> dt.date:
    return d.replace(day=1)


def _prev_month_same_day(d: dt.date) -> dt.date:
    y = d.year if d.month > 1 else d.year - 1
    m = d.month - 1 if d.month > 1 else 12
    last = monthrange(y, m)[1]
    return dt.date(y, m, min(d.day, last))


def _ytd_start(d: dt.date) -> dt.date:
    return dt.date(d.year, 1, 1)


def _prev_year_same_day(d: dt.date) -> dt.date:
    y = d.year - 1
    try:
        return dt.date(y, d.month, d.day)
    except ValueError:
        return dt.date(y, d.month, monthrange(y, d.month)[1])


def _qcol(alias: str, col: str) -> str:
    """Backtick-quote an alias.column safely."""
    return f"`{alias}`.`{col}`"


def _table_columns(table: str) -> List[str]:
    rows = frappe.db.sql(f"SHOW COLUMNS FROM `{table}`", as_dict=True)
    return [r["Field"] for r in rows]


def _resolve_date_column(table: str) -> str:
    """Find a plausible date column on the SalesDashBoard table."""
    cols = _table_columns(table)
    cols_lc = {c.lower(): c for c in cols}  # map lower->actual

    candidates = [
        "invoice date", "invoice_date", "invoicedate",
        "posting date", "posting_date",
        "date", "trans_date", "transaction_date",
        "docdate", "postingdate",
    ]
    for c in candidates:
        if c in cols_lc:
            return cols_lc[c]

    # Nothing matched: raise a clear error so you can map manually.
    raise frappe.ValidationError(
        f"No suitable date column found on `{table}`. "
        f"Available columns: {', '.join(cols)}. "
        f"Add a column alias like `Invoice Date` or `invoice_date` to your view/table, "
        f"or edit `_resolve_date_column` to map your actual field."
    )


def _filters_clause(extra: Dict[str, Any]) -> Tuple[str, List[Any]]:
    clauses = []
    params: List[Any] = []
    # Map only if the column exists; ignore silently if missing
    table = "tabSalesDashBoard"
    existing = set(_table_columns(table))
    mapping = {
        "territory": "Territory",
        "brand": "Brand",
        "warehouse": "warehouse",
        "company": "Company",
    }
    # Multi-territory from Access Profile
    if "Territory" in existing and extra.get("territories"):
        terrs = [t for t in (extra.get("territories") or []) if t]
        if len(terrs) == 1:
            clauses.append(_qcol("t", "Territory") + " = %s")
            params.append(terrs[0])
        elif terrs:
            clauses.append(_qcol("t", "Territory") + " IN %s")
            params.append(tuple(terrs))
    for k, col in mapping.items():
        if k == "territory" and extra.get("territories"):
            continue
        if col in existing and extra.get(k):
            clauses.append(_qcol("t", col) + " = %s")
            params.append(extra[k])
    return (" AND ".join(clauses), params)


# ------------------------
# Data access
# ------------------------

def _sum_sales_dashboard(
    date_from: dt.date,
    date_to: dt.date,
    *,
    extra: Dict[str, Any],
    date_col: str,
) -> Tuple[float, float]:
    """
    Returns (net_amount, cogs) sums from tabSalesDashBoard for the date window.
    Expects numeric columns: Net_Amount, COGS (adjust if yours differ).
    """
    where_extra, params_extra = _filters_clause(extra)
    where = [
        f"{_qcol('t', date_col)} >= %s",
        f"{_qcol('t', date_col)} <= %s",
    ]
    params: List[Any] = [date_from, date_to]
    if where_extra:
        where.append(where_extra)
        params.extend(params_extra)

    row = frappe.db.sql(
        f"""
        SELECT
            COALESCE(SUM({_qcol('t','Net_Amount')}), 0) AS net_amount,
            COALESCE(SUM({_qcol('t','COGS')}), 0)       AS cogs
        FROM `tabSalesDashBoard` AS `t`
        WHERE {" AND ".join(where)}
        """,
        params,
        as_dict=True,
    )[0]
    return float(row["net_amount"]), float(row["cogs"])


def _sum_outstanding_ar(
    date_from: dt.date,
    date_to: dt.date,
    *,
    company: Optional[str] = None,
    territories: Optional[List[str]] = None,
) -> float:
    where = [
        "`si`.`posting_date` >= %s",
        "`si`.`posting_date` <= %s",
        "`si`.`docstatus` <> 0",          # exclude Draft
        "`si`.`outstanding_amount` >= 0",
    ]
    params: List[Any] = [date_from, date_to]
    if company:
        where.append("`si`.`company` = %s")
        params.append(company)
    if territories:
        if len(territories) == 1:
            where.append("`si`.`territory` = %s")
            params.append(territories[0])
        else:
            where.append("`si`.`territory` IN %s")
            params.append(tuple(territories))

    row = frappe.db.sql(
        f"""
        SELECT COALESCE(SUM(`si`.`outstanding_amount`), 0) AS ar
        FROM `tabSales Invoice` AS `si`
        WHERE {" AND ".join(where)}
        """,
        params,
        as_dict=True,
    )[0]
    return float(row["ar"])


def _inventory_value(*, company: Optional[str] = None, warehouse: Optional[str] = None) -> float:
    where, params = [], []
    if warehouse:
        where.append("`b`.`warehouse` = %s")
        params.append(warehouse)
    # keep company filter only if your Bin has company column
    has_company = any(c.lower() == "company" for c in _table_columns("tabBin"))
    if company and has_company:
        where.append("`b`.`company` = %s")
        params.append(company)

    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    row = frappe.db.sql(
        f"""
        SELECT COALESCE(SUM(`b`.`valuation_rate` * `b`.`actual_qty`), 0) AS val
        FROM `tabBin` AS `b`
        {where_sql}
        """,
        params,
        as_dict=True,
    )[0]
    return float(row["val"])


def _pct_change(curr: float, prev: float) -> Tuple[float, str]:
    if prev == 0:
        return (0.0, "up" if curr >= 0 else "down")
    delta = ((curr - prev) / abs(prev)) * 100.0
    return (abs(round(delta, 2)), "up" if delta >= 0 else "down")


# ------------------------
# API
# ------------------------
@frappe.whitelist()
@frappe.read_only()
def get_dashboard_kpis(
    date: Optional[str] = None,
    company: Optional[str] = None,
    territory: Optional[str] = None,
    brand: Optional[str] = None,
    warehouse: Optional[str] = None,
    currency: str = "SAR",
) -> Dict[str, Any]:
    from erp_analysis.permissions.access_profile import resolve_territory_scope
    from erp_analysis.security import require_authenticated_user

    require_authenticated_user()
    today = _parse_date(date)

    # Resolve the date column ONCE (handles Invoice Date / invoice_date / Posting Date, etc.)
    date_col = "Invoice_Date"

    # Period windows
    mtd_from = _month_start(today)
    prev_mtd_to = _prev_month_same_day(today)
    prev_mtd_from = _month_start(prev_mtd_to)

    ytd_from = _ytd_start(today)
    prev_ytd_to = _prev_year_same_day(today)
    prev_ytd_from = _ytd_start(prev_ytd_to)

    scope = resolve_territory_scope(
        requested=territory, company=company, purpose="view", module="sales"
    )
    extra_filters: Dict[str, Any] = {
        "brand": brand,
        "warehouse": warehouse,
        "company": company,
    }
    if scope:
        extra_filters["territories"] = scope
    elif territory:
        extra_filters["territory"] = territory

    # SALES / COGS
    sales_mtd, cogs_mtd = _sum_sales_dashboard(mtd_from, today, extra=extra_filters, date_col=date_col)
    sales_prev_mtd, cogs_prev_mtd = _sum_sales_dashboard(prev_mtd_from, prev_mtd_to, extra=extra_filters, date_col=date_col)
    sales_ytd, _ = _sum_sales_dashboard(ytd_from, today, extra=extra_filters, date_col=date_col)
    sales_prev_ytd, _ = _sum_sales_dashboard(prev_ytd_from, prev_ytd_to, extra=extra_filters, date_col=date_col)

    # Gross Margin %
    margin_pct_mtd = round(((sales_mtd - cogs_mtd) / sales_mtd) * 100.0, 2) if sales_mtd else 0.0
    margin_pct_prev = round(((sales_prev_mtd - cogs_prev_mtd) / sales_prev_mtd) * 100.0, 2) if sales_prev_mtd else 0.0
    gm_change_pct, gm_change_dir = _pct_change(margin_pct_mtd, margin_pct_prev)

    # AR (MTD vs prev MTD)
    ar_mtd = _sum_outstanding_ar(mtd_from, today, company=company, territories=scope)
    ar_prev_mtd = _sum_outstanding_ar(prev_mtd_from, prev_mtd_to, company=company, territories=scope)
    ar_change_pct, ar_change_dir = _pct_change(ar_mtd, ar_prev_mtd)

    # Inventory
    inv_value = _inventory_value(company=company, warehouse=warehouse)

    sales_mtd_change_pct, sales_mtd_dir = _pct_change(sales_mtd, sales_prev_mtd)
    sales_ytd_change_pct, sales_ytd_dir = _pct_change(sales_ytd, sales_prev_ytd)

    return {
        "message": {
            "date": today.strftime("%A, %B %d, %Y"),
            "kpis": [
                {
                    "id": "sales_mtd",
                    "title": "SALES MTD",
                    "value": round(sales_mtd, 2),
                    "currency": currency,
                    "change_percentage": sales_mtd_change_pct,
                    "change_direction": sales_mtd_dir,
                    "change_period": "vs last period",
                    "background_gradient": ["#667eea", "#8e74e8"],
                },
                {
                    "id": "sales_ytd",
                    "title": "SALES YTD",
                    "value": round(sales_ytd, 2),
                    "currency": currency,
                    "change_percentage": sales_ytd_change_pct,
                    "change_direction": sales_ytd_dir,
                    "change_period": "vs last period",
                    "background_gradient": ["#ff6b81", "#ff4757"],
                },
                {
                    "id": "gross_margin",
                    "title": "GROSS MARGIN",
                    "value": round(margin_pct_mtd, 2),
                    "unit": "%",
                    "change_percentage": gm_change_pct,
                    "change_direction": gm_change_dir,
                    "change_period": "vs last period",
                    "background_gradient": ["#48dbfb", "#1dd1a1"],
                },
                {
                    "id": "outstanding_ar",
                    "title": "OUTSTANDING AR",
                    "value": round(ar_mtd, 2),
                    "currency": currency,
                    "change_percentage": ar_change_pct,
                    "change_direction": ar_change_dir,
                    "change_period": "vs last period",
                    "background_gradient": ["#2ed573", "#7bed9f"],
                },
                {
                    "id": "inventory_value",
                    "title": "INVENTORY VALUE",
                    "value": round(inv_value, 2),
                    "currency": currency,
                    "background_gradient": ["#ffa502", "#ffc048"],
                },
            ],
        }
    }

# -----------------------
# Main API
# -----------------------

@frappe.whitelist()
def get_today_sales_kpis(filters=None):
    """
    Returns JSON:
    {
      "message": {
        "current": {
          "total_sales": 30425902.03,
          "invoice_count": 3079,
          "avg_invoice_value": 9881.75,
          "unique_customers": 570,
          "cost_of_goods_sold": 0.0
        },
        "changes": {
          "total_sales": 12.5,
          "invoice_count": 8.3,
          "avg_invoice_value": 3.8
        },
        "period": "this_year"
      }
    }
    """
    from erp_analysis.security import require_authenticated_user

    require_authenticated_user()

    # Parse filters safely
    if isinstance(filters, str):
        try:
            filters = json.loads(filters or "{}")
        except Exception:
            filters = {}
    f = dict(filters or {})

    period = (f.get("period") or "this_year").lower()
    from_date, to_date = resolve_period_dates(period, f.get("from_date"), f.get("to_date"))

    # Optional filters
    company = f.get("company")
    territory = f.get("territory")
    customer_group = f.get("customer_group")
    include_cogs = bool(f.get("include_cogs", False))   # default off
    compare_yoy = bool(f.get("compare_yoy", True))      # default on

    # Build params and WHERE
    params = {
        "from_date": str(from_date),
        "to_date": str(to_date),
        "company": company,
        "territory": territory,
        "customer_group": customer_group,
    }
    where_sql = _build_where(params)

    # Current metrics
    cur_row = frappe.db.sql(
        f"""
        SELECT
            COALESCE(SUM(si.base_net_total), 0)      AS total_sales,
            COALESCE(COUNT(si.name), 0)              AS invoice_count,
            COALESCE(COUNT(DISTINCT si.customer), 0) AS unique_customers
        FROM `tabSales Invoice` si
        WHERE {where_sql}
        """,
        params,
        as_dict=True,
    )[0]

    total_sales = float(cur_row.total_sales or 0)
    invoice_count = int(cur_row.invoice_count or 0)
    unique_customers = int(cur_row.unique_customers or 0)
    avg_invoice_value = round(total_sales / invoice_count, 2) if invoice_count else 0.0

    # Optional COGS (from Stock Ledger Entry of Sales Invoice vouchers)
    cogs_value = 0.0
    if include_cogs:
        cogs_where = [
            "sle.voucher_type = 'Sales Invoice'",
            "sle.posting_date BETWEEN %(from_date)s AND %(to_date)s",
        ]
        if company:
            cogs_where.append("sle.company = %(company)s")
        cogs_sql = " AND ".join(cogs_where)

        cogs_row = frappe.db.sql(
            f"""
            SELECT COALESCE(-SUM(
                CASE WHEN sle.stock_value_difference < 0
                     THEN sle.stock_value_difference ELSE 0 END
            ), 0) AS cogs
            FROM `tabStock Ledger Entry` sle
            WHERE {cogs_sql}
            """,
            {"from_date": params["from_date"], "to_date": params["to_date"], "company": company},
            as_dict=True,
        )[0]
        cogs_value = float(cogs_row.cogs or 0)

    # YoY changes (default on)
    changes = {}
    if compare_yoy:
        prev_from = add_years(getdate(from_date), -1)
        prev_to = add_years(getdate(to_date), -1)
        prev_params = dict(params)
        prev_params["from_date"] = str(prev_from)
        prev_params["to_date"] = str(prev_to)

        prev_row = frappe.db.sql(
            f"""
            SELECT
                COALESCE(SUM(si.base_net_total), 0) AS total_sales,
                COALESCE(COUNT(si.name), 0)         AS invoice_count
            FROM `tabSales Invoice` si
            WHERE {where_sql}
            """,
            prev_params,
            as_dict=True,
        )[0]

        prev_sales = float(prev_row.total_sales or 0)
        prev_count = int(prev_row.invoice_count or 0)
        prev_avg = (prev_sales / prev_count) if prev_count else 0.0

        changes["total_sales"] = pct_change(total_sales, prev_sales)
        changes["invoice_count"] = pct_change(invoice_count, prev_count)
        changes["avg_invoice_value"] = pct_change(avg_invoice_value, prev_avg)

    # Shape output exactly
    return {
        "message": {
            "current": {
                "total_sales": round(total_sales, 2),
                "invoice_count": invoice_count,
                "avg_invoice_value": round(avg_invoice_value, 2),
                "unique_customers": unique_customers,
                "cost_of_goods_sold": round(cogs_value, 2),
            },
            "changes": changes,
            "period": period,
        }
    }


@frappe.whitelist(methods=["GET", "POST"], allow_guest=False)
def get_sales_dashboard(company=None, from_date=None, to_date=None, **kwargs):
	"""Mobile contract alias for dashboard sales summary."""
	from erp_analysis.dashboard import get_sales_dashboard_data

	return get_sales_dashboard_data(company, from_date, to_date)


@frappe.whitelist(methods=["GET", "POST"], allow_guest=False)
def get_salesperson_performance(company=None, period=None, from_date=None, to_date=None, limit=None, **kwargs):
	"""Mobile contract alias for sales performance ranking."""
	from erp_analysis.sales_performance import get_salesperson_performance as _impl

	return _impl(company=company, period=period, from_date=from_date, to_date=to_date, limit=limit)


@frappe.whitelist(methods=["GET", "POST"], allow_guest=False)
def get_product_performance(company=None, group_by=None, period=None, from_date=None, to_date=None, limit=None, **kwargs):
	"""Mobile contract alias for product performance ranking."""
	from erp_analysis.sales_performance import get_product_performance as _impl

	return _impl(company=company, group_by=group_by, period=period, from_date=from_date, to_date=to_date, limit=limit)
