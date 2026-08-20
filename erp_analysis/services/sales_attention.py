"""Sales attention alerts for mobile dashboards (declining territories, etc.)."""

from __future__ import annotations

from typing import Any, Optional

import frappe

from erp_analysis.services.analytics_sales import get_sales_analysis


def get_sales_attention(
	user: str,
	company: Optional[str] = None,
	section: str = "all",
	limit: int = 20,
	period: Optional[str] = "ytd",
	decline_threshold_pct: float = 25,
	stale_so_days: int = 90,
) -> dict[str, Any]:
	"""Structured sales attention alerts for mobile LIST / TABLE widgets."""
	del stale_so_days  # reserved for stale_orders section

	section = (section or "all").strip().lower()
	limit = max(1, min(int(limit or 20), 50))
	threshold = float(decline_threshold_pct or 25)
	period_key = (period or "ytd").strip().lower()

	alerts: list[dict[str, Any]] = []
	if section in ("all", "sales_down", "declining_territories", "territory"):
		alerts.extend(_territory_sales_down_alerts(user, company, period_key, threshold, limit))

	if section == "all":
		alerts.sort(key=lambda row: float(row.get("change_pct") or 0))
	else:
		alerts.sort(key=lambda row: float(row.get("change_pct") or 0))

	return {
		"data": alerts[:limit],
		"meta": {
			"schema_version": 1,
			"section": section,
			"period": period_key,
			"decline_threshold_pct": threshold,
			"count": min(len(alerts), limit),
		},
	}


def _territory_sales_down_alerts(
	user: str,
	company: Optional[str],
	period: str,
	decline_threshold_pct: float,
	limit: int,
) -> list[dict[str, Any]]:
	analysis = get_sales_analysis(
		user=user,
		company=company,
		dimension="territory",
		metric="net_sales",
		period=period,
		compare="ly",
		limit=max(limit, 20),
		order="desc",
	)

	alerts: list[dict[str, Any]] = []
	for row in analysis.get("data") or []:
		change_pct = row.get("change_pct")
		if change_pct is None or float(change_pct) > -abs(decline_threshold_pct):
			continue
		territory = row.get("label") or row.get("dimension_value")
		if not territory:
			continue
		metric_value = float(row.get("metric_value") or 0)
		change_val = float(change_pct)
		alerts.append(
			{
				"title": str(territory),
				"entity_name": str(territory),
				"value": round(metric_value, 2),
				"type": "sales_down",
				"severity": "danger" if change_val <= -40 else "warning",
				"description": f"Sales down {abs(change_val):.1f}% vs LY",
				"entity_type": "territory",
				"change_pct": round(change_val, 2),
			}
		)

	alerts.sort(key=lambda row: float(row.get("change_pct") or 0))
	return alerts
