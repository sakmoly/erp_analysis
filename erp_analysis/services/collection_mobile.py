"""Mobile-friendly shapes for collection APIs (native app + PWA)."""

from __future__ import annotations

from typing import Any

from erp_analysis.services.collection import (
	COLLECTION_AMOUNT_BASIS,
	COLLECTION_AMOUNT_FORMAT,
	format_collection_amount,
)


def enrich_collection_payments_for_mobile(payload: dict[str, Any]) -> dict[str, Any]:
	"""Duplicate totals into field names common mobile renderers read."""
	if not isinstance(payload, dict):
		return payload

	meta = payload.setdefault("meta", {})
	currency = meta.get("currency") or "SAR"
	summary = payload.setdefault("summary", {})
	net = float(summary.get("collected") or summary.get("net") or 0)
	display = summary.get("collected_display") or format_collection_amount(net, currency)

	summary["net"] = round(net, 2)
	summary["net_debit_credit"] = round(net, 2)
	summary["collection"] = round(net, 2)
	summary["total"] = round(net, 2)
	summary["collected_display"] = display
	summary.setdefault("amount_format", COLLECTION_AMOUNT_FORMAT)
	summary.setdefault("amount_basis", COLLECTION_AMOUNT_BASIS)

	mode_totals = summary.get("totals_by_mode_of_payment") or []
	payload["mode_totals"] = mode_totals
	payload["modes"] = mode_totals

	for item in payload.get("items") or []:
		if not isinstance(item, dict):
			continue
		paid_display = item.get("paid_amount_display") or format_collection_amount(
			item.get("paid_amount"), currency
		)
		item["paid_amount_display"] = paid_display
		item["display_amount"] = paid_display
		item["formatted_value"] = paid_display
		item["value_display"] = paid_display
		item.setdefault("amount_format", COLLECTION_AMOUNT_FORMAT)
		item["amount"] = item.get("paid_amount")
		item["value"] = item.get("paid_amount")

	meta.setdefault("amount_format", COLLECTION_AMOUNT_FORMAT)
	meta.setdefault("amount_basis", COLLECTION_AMOUNT_BASIS)

	payload["mobile"] = {
		"schema_version": 1,
		"amount_format": COLLECTION_AMOUNT_FORMAT,
		"amount_basis": COLLECTION_AMOUNT_BASIS,
		"prefer_summary_field": "collected_display",
		"prefer_line_amount_field": "paid_amount_display",
		"prefer_mode_totals_field": "mode_totals",
		"note": "Branch MoP totals are GL net (debit − credit). Use mode_totals for Cash Collection lines.",
	}
	return payload


def enrich_collection_dashboard_for_mobile(payload: dict[str, Any]) -> dict[str, Any]:
	if not isinstance(payload, dict):
		return payload

	meta = payload.setdefault("meta", {})
	currency = meta.get("currency") or "SAR"
	modes = payload.get("by_mode_of_payment") or []
	series: list[dict[str, Any]] = []
	for row in modes:
		if not isinstance(row, dict):
			continue
		net = float(row.get("collected") or row.get("net") or 0)
		label = row.get("mode_of_payment") or "Unassigned"
		series.append(
			{
				"label": label,
				"value": net,
				"dimension_value": label,
				"format": COLLECTION_AMOUNT_FORMAT,
				"amount_basis": row.get("amount_basis") or COLLECTION_AMOUNT_BASIS,
				"value_display": format_collection_amount(net, currency),
				"debit": row.get("debit"),
				"credit": row.get("credit"),
				"payment_count": row.get("payment_count"),
			}
		)

	payload["charts"] = {
		"by_mode_of_payment": {
			"series": series,
			"format": COLLECTION_AMOUNT_FORMAT,
			"amount_basis": COLLECTION_AMOUNT_BASIS,
		}
	}
	payload["mode_of_payment_totals"] = modes
	payload["mobile"] = {
		"schema_version": 1,
		"amount_format": COLLECTION_AMOUNT_FORMAT,
		"amount_basis": COLLECTION_AMOUNT_BASIS,
		"prefer_mode_totals_field": "by_mode_of_payment",
	}
	return payload
