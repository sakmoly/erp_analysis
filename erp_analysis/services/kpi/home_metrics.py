"""Home dashboard KPIs, health scores, and financial metrics."""

from __future__ import annotations

from datetime import date
from typing import Any, Optional

import frappe
from frappe.utils import add_years, getdate, nowdate

from erp_analysis.permissions.access_profile import resolve_territory_scope
from erp_analysis.services.kpi.gross_profit import _sales_and_cogs, get_gross_profit_period_kpis
from erp_analysis.services.kpi.inventory_summary import get_inventory_summary_kpis
from erp_analysis.services.kpi.receivables_summary import get_receivables_summary_kpis
from erp_analysis.services.kpi.sales import get_sales_period_kpis
from erp_analysis.services.payables import get_payables_summary
from erp_analysis.services.purchase import get_purchase_summary
from erp_analysis.services.sales_period import resolve_comparison_dates, resolve_period_dates, variance_block

HOME_KPI_CACHE_TTL = 120
HOME_KPI_CACHE_VERSION = 1

HOME_KPI_METRICS = frozenset(
	{
		"gross_profit",
		"gp_pct",
		"gross_profit_pct",
		"current_ratio",
		"operating_cash_flow",
		"net_profit",
		"health_score",
		"total_purchases",
		"purchases_ytd",
		"total_payable",
		"total_payables",
		"open_po_value",
	}
)

CURRENT_ASSET_TYPES = ("Bank", "Cash", "Receivable", "Stock", "Current Asset")
CURRENT_LIABILITY_TYPES = ("Payable", "Current Liability")
CASH_ACCOUNT_TYPES = ("Bank", "Cash")
INCOME_ROOT_TYPES = ("Income",)
EXPENSE_ROOT_TYPES = ("Expense",)


def is_home_kpi(metric_key: str) -> bool:
	return (metric_key or "").strip().lower() in HOME_KPI_METRICS


def _kpi_result(
	*,
	metric: str,
	label: str,
	value: float,
	value_ly: Optional[float] = None,
	fmt: str = "currency_compact",
	meta: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
	change_pct = None
	direction = "flat"
	if value_ly is not None:
		variance = variance_block(value, value_ly)
		change_pct = variance.get("change_pct")
		direction = variance.get("direction") or "flat"
	return {
		"metric": metric,
		"label": label,
		"value": round(float(value or 0), 2),
		"value_ly": round(float(value_ly), 2) if value_ly is not None else None,
		"change_pct": change_pct,
		"direction": direction,
		"meta": {"schema_version": 1, "format": fmt, **(meta or {})},
	}


def _clamp_score(value: float) -> float:
	return round(max(0.0, min(100.0, float(value or 0))), 2)


def _sales_health_score(company: Optional[str], territories: Optional[list[str]], as_of: date) -> float:
	kpis = get_sales_period_kpis(company=company, as_of=str(as_of), territories=territories)
	change = float(kpis.get("ytd_change_pct") or 0)
	return _clamp_score(50 + change * 0.75)


def _receivables_health_score(company: Optional[str]) -> float:
	kpis = get_receivables_summary_kpis(company=company)
	return _clamp_score(100 - float(kpis.get("overdue_pct") or 0))


def _inventory_health_score(company: Optional[str]) -> float:
	kpis = get_inventory_summary_kpis(company=company)
	low = float(kpis.get("low_stock_count") or 0)
	non_moving = float(kpis.get("non_moving_count") or 0)
	total_skus = _stocked_sku_count(company)
	if total_skus <= 0:
		return 100.0
	low_ratio = low / total_skus * 100
	non_moving_ratio = non_moving / total_skus * 100
	penalty = min(100.0, low_ratio * 0.35 + non_moving_ratio * 0.65)
	return _clamp_score(100 - penalty)


def _stocked_sku_count(company: Optional[str]) -> int:
	if not company:
		return 0
	row = frappe.db.sql(
		"""
		SELECT COUNT(DISTINCT b.item_code)
		FROM `tabBin` b
		INNER JOIN `tabWarehouse` w ON w.name = b.warehouse
		WHERE w.company = %s AND b.actual_qty > 0
		""",
		(company,),
	)[0][0]
	return int(row or 0)


def _payables_health_score(company: Optional[str]) -> float:
	kpis = get_payables_summary(company=company)
	return _clamp_score(100 - float(kpis.get("overdue_pct") or 0))


def _health_score(
	*,
	company: Optional[str],
	module_key: str,
	widget_key: str,
) -> dict[str, Any]:
	module = (module_key or "").strip().lower()
	key = (widget_key or "").strip().lower()
	if module in ("receivables", "receivable", "ar") or "receivables_health" in key:
		value = _receivables_health_score(company)
		label = "Receivables Health"
	elif module in ("inventory", "stock") or "inventory_health" in key:
		value = _inventory_health_score(company)
		label = "Inventory Health"
	elif module == "purchase" or "payables_health" in key:
		value = _payables_health_score(company)
		label = "Payables Health"
	else:
		territories = resolve_territory_scope(company=company, purpose="view", module="sales")
		value = _sales_health_score(company, territories, getdate(nowdate()))
		label = "Sales Performance"

	# Previous score: recompute with last-year sales change for sales; snapshot metrics stay flat.
	previous = None
	if "sales_health" in key:
		territories = resolve_territory_scope(company=company, purpose="view", module="sales")
		ly_date = add_years(getdate(nowdate()), -1)
		previous = _sales_health_score(company, territories, ly_date)

	return _kpi_result(metric="health_score", label=label, value=value, value_ly=previous, fmt="score")


def _period_value(
	period: str,
	mtd: float,
	ytd: float,
) -> float:
	return ytd if period == "ytd" else mtd


def _gross_profit_kpi(
	*,
	company: Optional[str],
	period: str,
	compare: Optional[str],
	to_date: Optional[str],
) -> dict[str, Any]:
	territories = resolve_territory_scope(company=company, purpose="view", module="sales")
	kpis = get_gross_profit_period_kpis(company=company, as_of=to_date, territories=territories)
	value = _period_value(period, float(kpis.get("mtd") or 0), float(kpis.get("ytd") or 0))
	value_ly = None
	if compare:
		end = getdate(to_date or nowdate())
		start, _, period_key = resolve_period_dates(None, to_date, period=period)
		comp_start, comp_end = resolve_comparison_dates(start, end, compare, period_key=period_key)
		ly_sales, ly_cogs = _sales_and_cogs(company, comp_start, comp_end, territories)
		value_ly = round(ly_sales - ly_cogs, 2)
	return _kpi_result(metric="gross_profit", label="Gross Profit", value=value, value_ly=value_ly)


def _gp_pct_kpi(
	*,
	company: Optional[str],
	period: str,
	compare: Optional[str],
	to_date: Optional[str],
) -> dict[str, Any]:
	territories = resolve_territory_scope(company=company, purpose="view", module="sales")
	kpis = get_gross_profit_period_kpis(company=company, as_of=to_date, territories=territories)
	value = float(kpis.get("gp_pct_ytd") or 0) if period == "ytd" else float(kpis.get("gp_pct_mtd") or 0)
	value_ly = None
	if compare:
		end = getdate(to_date or nowdate())
		start, _, period_key = resolve_period_dates(None, to_date, period=period)
		comp_start, comp_end = resolve_comparison_dates(start, end, compare, period_key=period_key)
		ly_sales, ly_cogs = _sales_and_cogs(company, comp_start, comp_end, territories)
		value_ly = round((ly_sales - ly_cogs) / ly_sales * 100, 2) if ly_sales > 0 else 0.0
	return _kpi_result(metric="gp_pct", label="GP Margin", value=value, value_ly=value_ly, fmt="percent")


def _total_purchases_kpi(
	*,
	company: Optional[str],
	period: str,
	compare: Optional[str],
	from_date: Optional[str],
	to_date: Optional[str],
) -> dict[str, Any]:
	start, end, period_key = resolve_period_dates(from_date, to_date, period=period)
	value = _purchase_invoice_total(company, start, end)
	value_ly = None
	if compare:
		comp_start, comp_end = resolve_comparison_dates(start, end, compare, period_key=period_key)
		value_ly = _purchase_invoice_total(company, comp_start, comp_end)
	return _kpi_result(metric="total_purchases", label="Total Purchases", value=value, value_ly=value_ly)


def _purchase_invoice_total(company: Optional[str], from_date: date, to_date: date) -> float:
	params: list[Any] = [from_date, to_date]
	company_sql = ""
	if company:
		company_sql = " AND company = %s"
		params.append(company)
	total = frappe.db.sql(
		f"""
		SELECT COALESCE(SUM(base_grand_total), 0)
		FROM `tabPurchase Invoice`
		WHERE docstatus = 1
		  AND posting_date BETWEEN %s AND %s
		  {company_sql}
		""",
		tuple(params),
	)[0][0]
	return round(float(total or 0), 2)


def _gl_balance_by_root_types(
	company: Optional[str],
	root_types: tuple[str, ...],
	from_date: Optional[date] = None,
	to_date: Optional[date] = None,
) -> float:
	if not company:
		return 0.0
	placeholders = ", ".join(["%s"] * len(root_types))
	params: list[Any] = [company, *root_types]
	date_sql = ""
	if from_date and to_date:
		date_sql = " AND gle.posting_date BETWEEN %s AND %s"
		params.extend([from_date, to_date])
	row = frappe.db.sql(
		f"""
		SELECT COALESCE(SUM(gle.debit - gle.credit), 0) AS balance
		FROM `tabGL Entry` gle
		INNER JOIN `tabAccount` acc ON acc.name = gle.account
		WHERE gle.is_cancelled = 0
		  AND gle.company = %s
		  AND acc.root_type IN ({placeholders})
		  {date_sql}
		""",
		tuple(params),
	)[0][0]
	return round(float(row or 0), 2)


def _gl_balance_by_account_types(
	company: Optional[str],
	account_types: tuple[str, ...],
	from_date: Optional[date] = None,
	to_date: Optional[date] = None,
) -> float:
	if not company:
		return 0.0
	placeholders = ", ".join(["%s"] * len(account_types))
	params: list[Any] = [company, *account_types]
	date_sql = ""
	if from_date and to_date:
		date_sql = " AND gle.posting_date BETWEEN %s AND %s"
		params.extend([from_date, to_date])
	row = frappe.db.sql(
		f"""
		SELECT COALESCE(SUM(gle.debit - gle.credit), 0) AS balance
		FROM `tabGL Entry` gle
		INNER JOIN `tabAccount` acc ON acc.name = gle.account
		WHERE gle.is_cancelled = 0
		  AND gle.company = %s
		  AND acc.account_type IN ({placeholders})
		  {date_sql}
		""",
		tuple(params),
	)[0][0]
	return round(float(row or 0), 2)


def _current_ratio_kpi(company: Optional[str]) -> dict[str, Any]:
	assets = abs(_gl_balance_by_account_types(company, CURRENT_ASSET_TYPES))
	liabilities = abs(_gl_balance_by_account_types(company, CURRENT_LIABILITY_TYPES))
	value = round(assets / liabilities, 2) if liabilities > 0 else 0.0
	return _kpi_result(metric="current_ratio", label="Current Ratio", value=value, fmt="decimal")


def _gl_net_profit_total(company: Optional[str], from_date: date, to_date: date) -> float:
	"""Period net profit from GL (Income − Expense), aligned with ERPNext P&L."""
	income = _gl_income_total(company, from_date, to_date)
	expense = _gl_expense_total(company, from_date, to_date)
	return round(income - expense, 2)


def _net_profit_kpi(
	*,
	company: Optional[str],
	period: str,
	from_date: Optional[str],
	to_date: Optional[str],
	compare: Optional[str] = None,
) -> dict[str, Any]:
	"""Net profit = GL Income − GL Expense for the period (same basis as ERPNext P&L)."""
	start, end, period_key = resolve_period_dates(from_date, to_date, period=period)
	value = _gl_net_profit_total(company, start, end)

	value_ly = None
	if compare:
		comp_start, comp_end = resolve_comparison_dates(start, end, compare, period_key=period_key)
		value_ly = _gl_net_profit_total(company, comp_start, comp_end)

	return _kpi_result(metric="net_profit", label="Net Profit", value=value, value_ly=value_ly)


def _gl_income_total(company: Optional[str], from_date: date, to_date: date) -> float:
	if not company:
		return 0.0
	row = frappe.db.sql(
		"""
		SELECT COALESCE(SUM(gle.credit - gle.debit), 0) AS total
		FROM `tabGL Entry` gle
		INNER JOIN `tabAccount` acc ON acc.name = gle.account
		WHERE gle.is_cancelled = 0
		  AND gle.company = %s
		  AND acc.root_type = 'Income'
		  AND gle.posting_date BETWEEN %s AND %s
		""",
		(company, from_date, to_date),
	)[0][0]
	return round(float(row or 0), 2)


def _gl_expense_total(company: Optional[str], from_date: date, to_date: date) -> float:
	if not company:
		return 0.0
	row = frappe.db.sql(
		"""
		SELECT COALESCE(SUM(gle.debit - gle.credit), 0) AS total
		FROM `tabGL Entry` gle
		INNER JOIN `tabAccount` acc ON acc.name = gle.account
		WHERE gle.is_cancelled = 0
		  AND gle.company = %s
		  AND acc.root_type = 'Expense'
		  AND gle.posting_date BETWEEN %s AND %s
		""",
		(company, from_date, to_date),
	)[0][0]
	return round(float(row or 0), 2)


_NON_OPERATING_EXPENSE_TYPES = (
	"Cost of Goods Sold",
	"Expenses Included In Valuation",
	"Stock Adjustment",
)


def _gl_operating_expense_total(company: Optional[str], from_date: date, to_date: date) -> float:
	"""GL operating expenses excluding COGS and stock valuation adjustments."""
	if not company:
		return 0.0
	placeholders = ", ".join(["%s"] * len(_NON_OPERATING_EXPENSE_TYPES))
	row = frappe.db.sql(
		f"""
		SELECT COALESCE(SUM(gle.debit - gle.credit), 0) AS total
		FROM `tabGL Entry` gle
		INNER JOIN `tabAccount` acc ON acc.name = gle.account
		WHERE gle.is_cancelled = 0
		  AND gle.company = %s
		  AND acc.root_type = 'Expense'
		  AND COALESCE(acc.account_type, '') NOT IN ({placeholders})
		  AND gle.posting_date BETWEEN %s AND %s
		""",
		(company, *_NON_OPERATING_EXPENSE_TYPES, from_date, to_date),
	)[0][0]
	return round(float(row or 0), 2)


def _operating_cash_flow_kpi(
	*,
	company: Optional[str],
	period: str,
	from_date: Optional[str],
	to_date: Optional[str],
) -> dict[str, Any]:
	start, end, _ = resolve_period_dates(from_date, to_date, period=period)
	value = _gl_balance_by_account_types(company, CASH_ACCOUNT_TYPES, start, end)
	return _kpi_result(metric="operating_cash_flow", label="Operating Cash Flow", value=value)


def _home_kpi_cache_key(
	*,
	company: Optional[str],
	metric: str,
	widget_key: str,
	period: str,
	compare: Optional[str],
	from_date: Optional[str],
	to_date: Optional[str],
) -> str:
	return (
		f"home_kpi:v{HOME_KPI_CACHE_VERSION}:{company or ''}:{metric}:{widget_key}:"
		f"{period}:{compare or ''}:{from_date or ''}:{to_date or ''}"
	)


def _home_kpi_is_cacheable(metric: str, widget_key: str) -> bool:
	key = (widget_key or "").strip().lower()
	if metric in ("current_ratio", "net_profit", "operating_cash_flow"):
		return True
	if metric == "health_score":
		return True
	if key in (
		"home_total_purchases_kpi",
		"home_total_payables_kpi",
		"home_gross_profit_kpi",
		"home_gp_margin_kpi",
	):
		return True
	return False


def get_home_kpi(
	*,
	user: str,
	company: Optional[str] = None,
	metric_key: str,
	module_key: str = "sales",
	widget_key: str = "",
	period: str = "mtd",
	compare: Optional[str] = None,
	from_date: Optional[str] = None,
	to_date: Optional[str] = None,
) -> dict[str, Any]:
	del user  # reserved for future scope filters
	metric = (metric_key or "").strip().lower()
	widget_key = (widget_key or "").strip().lower()

	cache_key = None
	if company and _home_kpi_is_cacheable(metric, widget_key):
		cache_key = _home_kpi_cache_key(
			company=company,
			metric=metric,
			widget_key=widget_key,
			period=period,
			compare=compare,
			from_date=from_date,
			to_date=to_date,
		)
		cached = frappe.cache().get_value(cache_key)
		if cached:
			return cached

	def _compute() -> dict[str, Any]:
		if metric == "health_score":
			return _health_score(company=company, module_key=module_key, widget_key=widget_key)

		if widget_key == "home_total_purchases_kpi":
			return _total_purchases_kpi(
				company=company,
				period=period,
				compare=compare,
				from_date=from_date,
				to_date=to_date,
			)

		if widget_key == "home_total_payables_kpi" or metric in ("total_payable", "total_payables"):
			kpis = get_payables_summary(company=company)
			return _kpi_result(metric="total_payable", label="Total Payables", value=float(kpis.get("total") or 0))

		if metric in ("gross_profit",):
			return _gross_profit_kpi(company=company, period=period, compare=compare, to_date=to_date)

		if metric in ("gp_pct", "gross_profit_pct"):
			return _gp_pct_kpi(company=company, period=period, compare=compare, to_date=to_date)

		if metric in ("total_purchases", "purchases_ytd"):
			return _total_purchases_kpi(
				company=company,
				period=period,
				compare=compare,
				from_date=from_date,
				to_date=to_date,
			)

		if metric in ("open_po_value", "open_value"):
			kpis = get_purchase_summary(company=company)
			return _kpi_result(
				metric=metric,
				label="Open PO Value",
				value=float(kpis.get("open_value") or 0),
			)

		if metric == "current_ratio":
			return _current_ratio_kpi(company)

		if metric == "net_profit":
			return _net_profit_kpi(
				company=company,
				period=period,
				from_date=from_date,
				to_date=to_date,
				compare=compare,
			)

		if metric == "operating_cash_flow":
			return _operating_cash_flow_kpi(
				company=company,
				period=period,
				from_date=from_date,
				to_date=to_date,
			)

		frappe.throw(f"Unsupported home KPI metric: {metric_key}")

	result = _compute()
	if cache_key:
		frappe.cache().set_value(cache_key, result, expires_in_sec=HOME_KPI_CACHE_TTL)
	return result
