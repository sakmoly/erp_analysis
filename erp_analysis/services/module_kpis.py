"""Non-sales module KPIs for mobile dashboard widgets."""

from __future__ import annotations

from typing import Any, Optional

import frappe
from frappe import _

from erp_analysis.services.kpi.collection import get_collection_period_kpis
from erp_analysis.services.kpi.inventory_summary import get_inventory_summary_kpis
from erp_analysis.services.kpi.receivables_summary import get_receivables_summary_kpis
from erp_analysis.services.kpi.home_metrics import _total_purchases_kpi
from erp_analysis.services.sales_orders import get_order_book_summary


RECEIVABLES_KPI_METRICS = frozenset(
	{
		"total_receivable",
		"total",
		"total_receivables",
		"overdue",
		"overdue_pct",
		"current",
		"not_due",
		"customer_count",
		"customers",
		"customer_advances",
		"total_customer_advances",
		"advance_customers",
	}
)

INVENTORY_KPI_METRICS = frozenset(
	{
		"inventory_value",
		"value",
		"stock_value",
		"stock_qty",
		"total_qty",
		"available_value",
		"reserved_value",
		"turnover",
		"inventory_turnover",
		"days_of_inventory",
		"avg_days",
		"days_of_cover",
		"low_stock",
		"low_stock_count",
		"non_moving",
		"non_moving_count",
	}
)

COLLECTION_KPI_METRICS = frozenset(
	{
		"collected_mtd",
		"collected_ytd",
		"collection_mtd",
		"collection_ytd",
		"collection_efficiency",
		"avg_collection_days",
		"customer_advances",
		"total_customer_advances",
		"advance_customers",
	}
)

PAYABLES_KPI_METRICS = frozenset({"total_payable", "total_payables", "overdue_payable", "payables_overdue"})

PURCHASE_KPI_METRICS = frozenset(
	{
		"open_po_value",
		"pending_receipt",
		"open_po_count",
		"pending_receipt_count",
		"total_purchases",
		"purchases_ytd",
	}
)

SALES_ORDERS_KPI_METRICS = frozenset(
	{
		"open_so_value",
		"pending_delivery",
		"open_so_count",
		"pending_delivery_count",
		"total_orders",
		"open_orders",
	}
)

RECEIVABLES_EXTENDED_METRICS = frozenset({"dso", "days_sales_outstanding"})


def is_module_kpi(module_key: str, metric_key: str) -> bool:
	module = (module_key or "").strip().lower()
	metric = (metric_key or "").strip().lower()
	if module in ("receivables", "receivable", "ar"):
		return metric in RECEIVABLES_KPI_METRICS or metric in RECEIVABLES_EXTENDED_METRICS
	if module in ("inventory", "stock"):
		return metric in INVENTORY_KPI_METRICS
	if module == "collection":
		return metric in COLLECTION_KPI_METRICS
	if module in ("purchase", "purchasing", "purchases"):
		return metric in PURCHASE_KPI_METRICS
	if module in ("payables", "payable", "ap"):
		return metric in PAYABLES_KPI_METRICS
	if module in ("sales_orders", "sales_order"):
		return metric in SALES_ORDERS_KPI_METRICS
	return False


def get_module_kpi(
	*,
	user: str,
	company: Optional[str] = None,
	module_key: str,
	metric_key: str,
	period: str = "mtd",
	filters: Any = None,
) -> dict[str, Any]:
	module = (module_key or "").strip().lower()
	metric = (metric_key or "").strip().lower()
	period_key = (period or "mtd").strip().lower()

	if module in ("receivables", "receivable", "ar"):
		return _receivables_kpi(company, metric, filters=filters)
	if module in ("inventory", "stock"):
		return _inventory_kpi(company, metric)
	if module == "collection":
		return _collection_kpi(company, metric, period_key, filters=filters)
	if module in ("purchase", "purchasing", "purchases"):
		return _purchase_kpi(company, metric, period_key)
	if module in ("payables", "payable", "ap"):
		return _payables_kpi(company, metric)
	if module in ("sales_orders", "sales_order"):
		return _sales_orders_kpi(company, metric, user=user, filters=filters)

	frappe.throw(
		_("Unsupported module KPI: {0}/{1}").format(module_key, metric_key),
		frappe.ValidationError,
	)


def _kpi_result(*, metric: str, label: str, value: float, fmt: str = "currency_compact") -> dict[str, Any]:
	return {
		"metric": metric,
		"label": label,
		"value": round(float(value or 0), 2),
		"value_ly": None,
		"change_pct": None,
		"direction": "flat",
		"meta": {"schema_version": 1, "format": fmt},
	}


def _territory_scope_from_filters(filters: Any) -> tuple[Optional[str], Optional[list[str]]]:
	from erp_analysis.services.analytics_dimensions import parse_logical_filters

	parsed = parse_logical_filters(filters)
	territories = [
		str(t).strip() for t in (parsed.get("territory") or []) if t is not None and str(t).strip()
	]
	if len(territories) == 1:
		return territories[0], None
	if len(territories) > 1:
		return None, territories
	return None, None


def _receivables_kpi(company: Optional[str], metric: str, *, filters: Any = None) -> dict[str, Any]:
	territory, territories = _territory_scope_from_filters(filters)
	kpis = get_receivables_summary_kpis(
		company=company,
		territory=territory,
		territories=territories,
	)
	total = float(kpis["total"])
	overdue = float(kpis["overdue"])

	if metric in ("total_receivable", "total", "total_receivables"):
		return _kpi_result(metric=metric, label="Total Receivable", value=total)
	if metric == "overdue":
		return _kpi_result(metric=metric, label="Overdue", value=overdue)
	if metric == "overdue_pct":
		return _kpi_result(
			metric=metric,
			label="Overdue %",
			value=kpis["overdue_pct"],
			fmt="percent",
		)
	if metric in ("current", "not_due"):
		return _kpi_result(metric=metric, label="Not Yet Due", value=max(total - overdue, 0))
	if metric in ("customer_count", "customers"):
		count = _receivables_customer_count(company, territory=territory, territories=territories)
		return _kpi_result(metric=metric, label="Customers Owing", value=count, fmt="integer")
	if metric in ("customer_advances", "total_customer_advances"):
		from erp_analysis.services.collection import get_customer_advances_summary

		summary = get_customer_advances_summary(
			company=company,
			territory=territory,
			territories=territories,
		)
		return _kpi_result(
			metric=metric,
			label="Customer Advances",
			value=summary.get("total_advance") or 0,
		)
	if metric in ("advance_customers",):
		from erp_analysis.services.collection import get_customer_advances_summary

		summary = get_customer_advances_summary(
			company=company,
			territory=territory,
			territories=territories,
		)
		return _kpi_result(
			metric=metric,
			label="Customers with Advance",
			value=summary.get("customer_count") or 0,
			fmt="integer",
		)
	if metric in ("dso", "days_sales_outstanding"):
		snap = _receivables_snapshot(company)
		return _kpi_result(
			metric=metric,
			label="DSO",
			value=snap.get("dso") or 0,
			fmt="integer",
		)
	frappe.throw(_("Unsupported receivables metric: {0}").format(metric), frappe.ValidationError)


def _receivables_snapshot(company: Optional[str]) -> dict[str, Any]:
	from erp_analysis.receivables import get_receivables_snapshot

	return get_receivables_snapshot(company=company) or {}


def _receivables_customer_count(
	company: Optional[str],
	*,
	territory: Optional[str] = None,
	territories: Optional[list[str]] = None,
) -> int:
	if not company:
		return 0
	from erp_analysis.permissions.access_profile import resolve_territory_scope, si_territory_sql

	if territories is not None:
		scope = territories
	else:
		scope = resolve_territory_scope(
			requested=territory,
			company=company,
			purpose="view",
			module="receivables",
		)
	terr_sql, terr_params = si_territory_sql(scope, field="territory")
	row = frappe.db.sql(
		f"""
		SELECT COUNT(DISTINCT customer) AS cnt
		FROM `tabSales Invoice`
		WHERE docstatus = 1 AND outstanding_amount > 0 AND company = %s
		{terr_sql}
		""",
		tuple([company] + terr_params),
	)[0][0]
	return int(row or 0)


def _inventory_kpi(company: Optional[str], metric: str) -> dict[str, Any]:
	kpis = get_inventory_summary_kpis(company=company)
	if metric in ("inventory_value", "value", "stock_value"):
		return _kpi_result(metric=metric, label="Stock Value", value=kpis["value"])
	if metric in ("stock_qty", "total_qty"):
		return _kpi_result(
			metric=metric,
			label="Stock Quantity",
			value=kpis["stock_qty"],
			fmt="integer",
		)
	if metric == "available_value":
		return _kpi_result(metric=metric, label="Available Value", value=kpis["available_value"])
	if metric == "reserved_value":
		return _kpi_result(metric=metric, label="Reserved Value", value=kpis["reserved_value"])
	if metric in ("turnover", "inventory_turnover"):
		return _kpi_result(
			metric=metric,
			label="Inventory Turnover",
			value=kpis["turnover"],
			fmt="decimal",
		)
	if metric in ("days_of_inventory", "avg_days", "days_of_cover"):
		from erp_analysis.services.stock_cover import get_stock_cover_payload

		cover = get_stock_cover_payload(company=company)
		days = float((cover.get("kpis") or {}).get("avg_cover_days") or 0)
		if days <= 0:
			days = float(kpis["days_of_inventory"])
		return _kpi_result(
			metric=metric,
			label="Days of Inventory",
			value=days,
			fmt="integer",
		)
	if metric in ("low_stock", "low_stock_count"):
		return _kpi_result(
			metric=metric,
			label="Low Stock Items",
			value=kpis["low_stock_count"],
			fmt="integer",
		)
	if metric in ("non_moving", "non_moving_count"):
		return _kpi_result(
			metric=metric,
			label="Non-Moving SKUs",
			value=kpis["non_moving_count"],
			fmt="integer",
		)
	frappe.throw(_("Unsupported inventory metric: {0}").format(metric), frappe.ValidationError)


def _collection_kpi(
	company: Optional[str],
	metric: str,
	period: str,
	*,
	filters: Any = None,
) -> dict[str, Any]:
	if metric in ("customer_advances", "total_customer_advances", "advance_customers"):
		territory, territories = _territory_scope_from_filters(filters)
		from erp_analysis.services.collection import get_customer_advances_summary

		summary = get_customer_advances_summary(
			company=company,
			territory=territory,
			territories=territories,
		)
		if metric in ("advance_customers",):
			return _kpi_result(
				metric=metric,
				label="Customers with Advance",
				value=summary.get("customer_count") or 0,
				fmt="integer",
			)
		return _kpi_result(
			metric=metric,
			label="Customer Advances",
			value=summary.get("total_advance") or 0,
		)

	kpis = get_collection_period_kpis(company=company)
	if metric in ("collected_mtd", "collection_mtd") or (metric == "collected" and period == "mtd"):
		return _kpi_result(
			metric=metric,
			label="Collected MTD",
			value=kpis.get("mtd") or 0,
			fmt="currency_integer",
		)
	if metric in ("collected_ytd", "collection_ytd") or (metric == "collected" and period == "ytd"):
		return _kpi_result(
			metric=metric,
			label="Collected YTD",
			value=kpis.get("ytd") or 0,
			fmt="currency_integer",
		)
	if metric == "collection_efficiency":
		perf = _receivables_performance(company)
		return _kpi_result(
			metric=metric,
			label="Collection Efficiency",
			value=perf.get("collectionEfficiency") or 0,
			fmt="percent",
		)
	if metric in ("avg_collection_days", "avg_collection_days"):
		snap = _receivables_snapshot(company)
		return _kpi_result(
			metric=metric,
			label="Avg. Collection Days",
			value=snap.get("averageCollectionPeriod") or 0,
			fmt="integer",
		)
	frappe.throw(_("Unsupported collection metric: {0}").format(metric), frappe.ValidationError)


def _receivables_performance(company: Optional[str]) -> dict[str, Any]:
	from erp_analysis.receivables import get_receivables_performance

	return get_receivables_performance(company=company, limit=5) or {}


def _payables_kpi(company: Optional[str], metric: str) -> dict[str, Any]:
	kpis = get_payables_summary(company=company)
	total = float(kpis.get("total") or 0)
	overdue = float(kpis.get("overdue") or 0)
	if metric in ("total_payable", "total_payables"):
		return _kpi_result(metric=metric, label="Total Payables", value=total)
	if metric in ("overdue_payable", "payables_overdue"):
		return _kpi_result(metric=metric, label="Overdue Payables", value=overdue)
	frappe.throw(_("Unsupported payables metric: {0}").format(metric), frappe.ValidationError)


def _purchase_kpi(company: Optional[str], metric: str, period: str = "mtd") -> dict[str, Any]:
	if metric in ("total_purchases", "purchases_ytd"):
		return _total_purchases_kpi(company=company, period=period, compare=None, from_date=None, to_date=None)
	kpis = get_purchase_summary(company=company)
	if metric in ("open_po_value", "open_value"):
		return _kpi_result(metric=metric, label="Open PO Value", value=kpis.get("open_value") or 0)
	if metric in ("pending_receipt", "pending_receipt_value"):
		return _kpi_result(metric=metric, label="Pending Receipt", value=kpis.get("pending_receipt_value") or 0)
	if metric in ("open_po_count",):
		return _kpi_result(metric=metric, label="Open POs", value=kpis.get("open_count") or 0, fmt="integer")
	if metric in ("pending_receipt_count",):
		return _kpi_result(
			metric=metric,
			label="Pending Receipt POs",
			value=kpis.get("pending_receipt_count") or 0,
			fmt="integer",
		)
	frappe.throw(_("Unsupported purchase metric: {0}").format(metric), frappe.ValidationError)


def _sales_orders_kpi(
	company: Optional[str],
	metric: str,
	*,
	user: Optional[str] = None,
	filters: Any = None,
) -> dict[str, Any]:
	from erp_analysis.services.sales_orders import get_open_so_summary, get_order_book_summary

	count_metrics = ("open_so_count", "pending_delivery_count", "total_orders", "open_orders")
	if metric in count_metrics or metric in ("open_so_value", "pending_delivery", "pending_delivery_value"):
		summary = get_open_so_summary(user=user, company=company, filters=filters)
		if metric in ("open_so_value", "open_value", "pending_delivery", "pending_delivery_value"):
			return _kpi_result(
				metric=metric,
				label="Pending Delivery" if "pending" in metric else "Open SO Value",
				value=summary.get("open_so_value") or 0,
			)
		return _kpi_result(
			metric=metric,
			label="Open Sales Orders",
			value=summary.get("open_so_count") or 0,
			fmt="integer",
		)

	kpis = get_order_book_summary(company=company)
	if metric in ("open_so_value", "open_value"):
		return _kpi_result(metric=metric, label="Open SO Value", value=kpis.get("open_value") or 0)
	if metric in ("pending_delivery", "pending_delivery_value"):
		return _kpi_result(metric=metric, label="Pending Delivery", value=kpis.get("pending_delivery_value") or 0)
	if metric in ("open_so_count",):
		return _kpi_result(metric=metric, label="Open Sales Orders", value=kpis.get("open_count") or 0, fmt="integer")
	if metric in ("pending_delivery_count",):
		return _kpi_result(
			metric=metric,
			label="Pending Delivery SOs",
			value=kpis.get("pending_delivery_count") or 0,
			fmt="integer",
		)
	frappe.throw(_("Unsupported sales orders metric: {0}").format(metric), frappe.ValidationError)
