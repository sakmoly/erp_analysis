"""Smoke-test all mobile APIs registered for erp_analysis."""

from __future__ import annotations

import json
import traceback
from typing import Any

import frappe

from erp_analysis.patches.sync_mobile_access_registry import MOBILE_API_REGISTRY

# Extra platform endpoints mobile uses at boot.
EXTRA_APIS: tuple[tuple[str, dict[str, Any]], ...] = (
	("erp_analysis.api.health", {}),
	("erp_analysis.api.get_mobile_config", {}),
	("erp_analysis.api.get_my_access", {}),
	("erp_analysis.config.get_client_id", {}),
)

# Registry object_keys used for Access Profile only (not standalone HTTP methods).
ACCESS_ONLY_KEYS = frozenset(
	{
		"erp_analysis.approvals.sales_invoice",
		"erp_analysis.approvals.delivery_note",
		"erp_analysis.approvals.get_sales_invoice",
		"erp_analysis.approvals.get_delivery_note",
		"erp_analysis.approvals.get_material_request",
		"erp_analysis.approvals.get_Payment_Request",
		"erp_analysis.approvals.get_stock_entry",
	}
)
API_KWARGS: dict[str, dict[str, Any]] = {
	"erp_analysis.receivables.get_customer_statement": {
		"customer": "__first_customer__",
	},
	"erp_analysis.customer_360.get_customer_360": {"customer": "__first_customer__"},
	"erp_analysis.customer.get_customer_360": {"customer": "__first_customer__"},
	"erp_analysis.customer.search_customers": {"query": "a", "limit": 5},
	"erp_analysis.inventory.get_inventory_health": {},
	"erp_analysis.inventory.get_dead_stock": {"min_days": 90, "limit": 10},
	"erp_analysis.customer_360.get_customer": {"customer": "__first_customer__"},
	"erp_analysis.inventory.get_inventory_hierarchy": {"level": "category"},
	"erp_analysis.stock.get_inventory_hierarchy": {"level": "category"},
	"printechs_utility.inventory.get_inventory_hierarchy": {"level": "category"},
	"erp_analysis.inventory.get_inventory_items": {"brand": "__legacy_brand__"},
	"erp_analysis.stock.get_inventory_items": {"item_group": "__legacy_brand__"},
	"printechs_utility.inventory.get_inventory_items": {"item_group": "__legacy_brand__"},
	"erp_analysis.catalogue.get_catalogue_pages": {"catalogue_id": "__first_catalogue__"},
	"erp_analysis.catalogue.get_catalogue_detail": {"catalogue_id": "__first_catalogue__"},
	"erp_analysis.catalogue.get_catalogue_flip_url": {"catalogue_id": "__first_catalogue__"},
}


def _first_customer() -> str | None:
	return frappe.db.get_value("Customer", {"disabled": 0}, "name", order_by="modified desc")


def _first_catalogue() -> str | None:
	if frappe.db.exists("DocType", "E Catalogue"):
		return frappe.db.get_value("E Catalogue", {"enabled": 1}, "name", order_by="modified desc")
	return None


def _legacy_brand() -> str | None:
	rows = frappe.call("erp_analysis.inventory.get_inventory_hierarchy", level="brand", category="Retail")
	if rows:
		return rows[0].get("brand")
	return None


def _resolve_kwargs(method: str, kwargs: dict[str, Any]) -> dict[str, Any]:
	resolved = dict(kwargs)
	for key, value in list(resolved.items()):
		if value == "__first_customer__":
			customer = _first_customer()
			if not customer:
				raise ValueError("No Customer found for smoke test")
			resolved[key] = customer
		elif value == "__first_catalogue__":
			catalogue = _first_catalogue()
			if not catalogue:
				raise ValueError("No published E Catalogue found for smoke test")
			resolved[key] = catalogue
		elif value == "__legacy_brand__":
			brand = _legacy_brand()
			if not brand:
				raise ValueError("No brand row for inventory legacy smoke test")
			resolved[key] = brand
	return resolved


def _method_importable(method: str) -> bool:
	try:
		frappe.get_attr(method)
		return True
	except Exception:
		return False


def _is_whitelisted(method: str) -> bool:
	try:
		fn = frappe.get_attr(method)
	except Exception:
		return False
	# frappe.whitelisted stores bare function objects, not dotted paths.
	return fn in frappe.whitelisted


def _call_method(method: str, kwargs: dict[str, Any]) -> Any:
	fn = frappe.get_attr(method)
	return fn(**kwargs)


DEFAULT_SMOKE_USER = "sakeer@printechs.com"


def run_smoke_tests(user: str | None = DEFAULT_SMOKE_USER) -> dict[str, Any]:
	"""Run smoke tests. Returns summary dict."""
	previous_user = frappe.session.user
	test_user = user
	if test_user and not frappe.db.exists("User", test_user):
		test_user = previous_user
	if test_user:
		frappe.set_user(test_user)

	results: list[dict[str, Any]] = []
	methods = [m for m, _ in MOBILE_API_REGISTRY] + [m for m, _ in EXTRA_APIS]

	try:
		for method in methods:
			label = dict(MOBILE_API_REGISTRY).get(method, method)
			entry: dict[str, Any] = {"method": method, "label": label}

			if method in ACCESS_ONLY_KEYS:
				entry.update({"status": "SKIP", "error": "Access object key only"})
				results.append(entry)
				continue

			if not _method_importable(method):
				entry.update({"status": "FAIL", "error": "Method not importable"})
				results.append(entry)
				continue

			if not _is_whitelisted(method):
				entry.update({"status": "FAIL", "error": "Not whitelisted"})
				results.append(entry)
				continue

			try:
				kwargs = _resolve_kwargs(method, dict(API_KWARGS.get(method, {})))
			except Exception as exc:
				entry.update({"status": "SKIP", "error": f"Missing test data: {exc}"})
				results.append(entry)
				continue

			# Skip side-effect POST-only methods in smoke test
			if method in (
				"erp_analysis.approvals.approve_document",
				"erp_analysis.approvals.reject_document",
				"erp_analysis.customer_notifications.send_statement_pdf",
				"erp_analysis.customer_notifications.get_statement_pdf",
			):
				entry.update({"status": "SKIP", "error": "Side-effect POST — whitelisted only"})
				results.append(entry)
				continue

			try:
				result = _call_method(method, kwargs)
				entry.update(
					{
						"status": "OK",
						"result_type": type(result).__name__,
						"preview": _preview(result),
					}
				)
			except Exception as exc:
				entry.update(
					{
						"status": "FAIL",
						"error": str(exc),
						"traceback": traceback.format_exc(limit=3),
					}
				)
			results.append(entry)
	finally:
		frappe.set_user(previous_user)

	ok = sum(1 for r in results if r["status"] == "OK")
	fail = sum(1 for r in results if r["status"] == "FAIL")
	skip = sum(1 for r in results if r["status"] == "SKIP")

	return {
		"ok": ok,
		"fail": fail,
		"skip": skip,
		"total": len(results),
		"results": results,
	}


def _preview(result: Any, max_len: int = 120) -> str:
	try:
		text = json.dumps(result, default=str)
	except Exception:
		text = repr(result)
	if len(text) > max_len:
		return text[: max_len - 3] + "..."
	return text


@frappe.whitelist()
def run_mobile_api_smoke_tests(user: str | None = None):
	"""Whitelisted entry for bench execute / desk."""
	return run_smoke_tests(user=user)


def execute():
	"""Patch entry — log summary only."""
	summary = run_smoke_tests()
	frappe.logger().info(
		f"mobile_api_smoke: ok={summary['ok']} fail={summary['fail']} skip={summary['skip']}"
	)
	if summary["fail"]:
		failed = [r["method"] for r in summary["results"] if r["status"] == "FAIL"]
		frappe.log_error(
			title="Mobile API smoke test failures",
			message="\n".join(failed),
		)
