"""Per-request KPI cache for dashboard board batch loads."""

from __future__ import annotations

from typing import Any, Optional

_CACHE: dict[tuple, dict[str, Any]] = {}


def reset_batch_kpi_cache() -> None:
	_CACHE.clear()


def _cache_key(
	company: Optional[str],
	metric: str,
	period: str,
	compare: Optional[str],
	filters_key: str,
) -> tuple:
	return (company or "", metric, period or "", compare or "", filters_key or "")


def get_cached_kpi(
	company: Optional[str],
	metric: str,
	period: str,
	compare: Optional[str],
	filters_key: str,
) -> Optional[dict[str, Any]]:
	return _CACHE.get(_cache_key(company, metric, period, compare, filters_key))


def set_cached_kpi(
	company: Optional[str],
	metric: str,
	period: str,
	compare: Optional[str],
	filters_key: str,
	payload: dict[str, Any],
) -> None:
	_CACHE[_cache_key(company, metric, period, compare, filters_key)] = payload


def warm_batch_kpi_cache(
	user: str,
	company: Optional[str],
	widgets: list[dict[str, Any]],
) -> None:
	"""Pre-resolve module KPIs referenced by KPI widgets on one board."""
	metrics: set[tuple[str, str]] = set()
	for widget in widgets:
		if (widget.get("widget_type") or "").upper() != "KPI":
			continue
		module_key = (widget.get("module_key") or "").strip().lower()
		metric_key = (widget.get("metric_key") or "").strip().lower()
		if module_key and metric_key:
			metrics.add((module_key, metric_key))

	if not metrics:
		return

	from erp_analysis.services.module_kpis import get_module_kpi, is_module_kpi

	for module_key, metric_key in metrics:
		if not is_module_kpi(module_key, metric_key):
			continue
		cache_metric = f"{module_key}:{metric_key}"
		if get_cached_kpi(company, cache_metric, "mtd", None, "") is not None:
			continue
		kpi = get_module_kpi(
			user=user,
			company=company,
			module_key=module_key,
			metric_key=metric_key,
			period="mtd",
		)
		set_cached_kpi(company, cache_metric, "mtd", None, "", kpi)
