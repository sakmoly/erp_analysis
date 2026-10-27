"""Create tabSalesDashBoard on new sites (idempotent). Runs before SI view setup."""

from __future__ import annotations

import os

import frappe

from erp_analysis.patches.setup_sales_dashboard_from_si import (
	TABLE,
	_apply_schema,
	_create_view,
	_add_unique_index,
)


def _run_create_table_sql() -> None:
	app_path = frappe.get_app_path("erp_analysis")
	sql_path = os.path.join(app_path, "patches", "sql", "create_tab_sales_dashboard.sql")
	with open(sql_path, encoding="utf-8") as handle:
		sql = handle.read().strip()
	if not sql:
		frappe.throw(f"Empty SQL at {sql_path}")
	frappe.db.sql_ddl(sql)


def ensure_sales_dashboard_table(*, apply_view: bool = True) -> dict:
	"""Create SDB table + indexes/views when missing. Safe to call from migrate."""
	created = False
	if not frappe.db.table_exists("SalesDashBoard"):
		_run_create_table_sql()
		created = True

	if not frappe.db.table_exists("SalesDashBoard"):
		return {"ok": False, "reason": "create_tab_sales_dashboard failed"}

	_apply_schema()

	view_ok = False
	view_error = None
	if apply_view:
		try:
			_create_view()
			view_ok = True
		except Exception as exc:
			view_error = str(exc)
			frappe.log_error(
				title="ensure_sales_dashboard_table view",
				message=frappe.get_traceback(),
			)

	unique_index = False
	try:
		_add_unique_index()
		unique_index = True
	except Exception:
		frappe.log_error(
			title="ensure_sales_dashboard_table unique index",
			message=frappe.get_traceback(),
		)

	frappe.db.commit()
	return {
		"ok": True,
		"table_created": created,
		"view_ok": view_ok,
		"view_error": view_error,
		"unique_index": unique_index,
		"row_count": frappe.db.sql(f"SELECT COUNT(*) FROM `{TABLE}`")[0][0],
	}


def execute():
	return ensure_sales_dashboard_table(apply_view=True)
