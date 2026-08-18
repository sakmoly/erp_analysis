"""Period and comparison helpers for sales analytics KPIs."""

from __future__ import annotations

from datetime import date
from typing import Any, Optional

import frappe
from frappe import _
from frappe.utils import add_months, add_years, get_first_day, get_last_day, getdate, nowdate

ALLOWED_PERIODS = frozenset({"mtd", "ytd", "qtd", "today", "custom"})
ALLOWED_COMPARE = frozenset({"ly", "previous_year", "previous_period"})


def normalize_compare(compare: Optional[str]) -> Optional[str]:
	if not compare:
		return None
	key = str(compare).strip().lower()
	if key in ("ly", "previous_year"):
		return "ly"
	if key == "previous_period":
		return "previous_period"
	return key


def validate_compare(compare: Optional[str]) -> Optional[str]:
	key = normalize_compare(compare)
	if key and key not in ALLOWED_COMPARE:
		frappe.throw(_("Unsupported compare mode: {0}").format(compare), frappe.ValidationError)
	return key


def resolve_period_dates(
	from_date: Optional[str],
	to_date: Optional[str],
	*,
	period: Optional[str] = None,
) -> tuple[date, date, str]:
	if from_date and to_date:
		return getdate(from_date), getdate(to_date), "custom"

	key = (period or "mtd").strip().lower()
	today = getdate(to_date or nowdate())

	if key == "today":
		return today, today, "today"
	if key == "ytd":
		return date(today.year, 1, 1), today, "ytd"
	if key == "qtd":
		q_start_month = ((today.month - 1) // 3) * 3 + 1
		return date(today.year, q_start_month, 1), today, "qtd"
	# default mtd
	return get_first_day(today), today, "mtd"


def resolve_comparison_dates(
	start: date,
	end: date,
	compare: Optional[str],
	*,
	period_key: str = "mtd",
) -> tuple[date, date]:
	if not compare:
		return start, end
	if compare == "ly":
		return add_years(start, -1), add_years(end, -1)
	if compare == "previous_period":
		if period_key == "today":
			prev = add_years(end, -1)
			return prev, prev
		if period_key == "ytd":
			days = (end - start).days
			prev_end = add_years(end, -1)
			return add_years(start, -1), min(prev_end, add_years(start, -1).replace(month=12, day=31)) if days else prev_end
		# mtd / qtd / custom — shift back one month block
		prev_end = add_months(end, -1)
		prev_start = add_months(start, -1)
		return prev_start, prev_end
	return start, end


def pct_change(current: float, previous: float) -> Optional[float]:
	if previous <= 0:
		return None if current <= 0 else 100.0
	return round((current - previous) / previous * 100, 2)


def variance_block(current: float, previous: float) -> dict[str, Any]:
	change = pct_change(current, previous)
	if change is None:
		direction = "flat"
	elif change > 0:
		direction = "up"
	elif change < 0:
		direction = "down"
	else:
		direction = "flat"
	return {
		"variance": round(current - previous, 2),
		"change_pct": change,
		"direction": direction,
	}


def merge_compare_rows(
	current_rows: list[dict[str, Any]],
	compare_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
	comp_map = {
		str(row.get("dimension_value")): float(row.get("metric_value") or 0)
		for row in compare_rows
		if row.get("dimension_value") not in (None, "")
	}
	for row in current_rows:
		dim_val = row.get("dimension_value")
		if dim_val is None or str(dim_val) == "":
			continue
		comp_val = comp_map.get(str(dim_val))
		row["metric_value_ly"] = round(comp_val, 2) if comp_val is not None else None
		row["change_pct"] = pct_change(float(row.get("metric_value") or 0), comp_val) if comp_val is not None else None
	return current_rows
