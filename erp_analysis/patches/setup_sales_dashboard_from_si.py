"""SalesDashBoard: SI-sourced view, schema columns, indexes; optional full refresh."""

from __future__ import annotations

import os

import frappe


TABLE = "tabSalesDashBoard"
VIEW = "ViewSalesDashBoardFromSI"
UNIQUE_NAME = "uniq_sdb_invoice_line"


def _column_names() -> set[str]:
	if not frappe.db.table_exists("SalesDashBoard"):
		return set()
	return {c["Field"] for c in frappe.db.sql(f"SHOW COLUMNS FROM `{TABLE}`", as_dict=True)}


def _apply_schema() -> None:
	cols = _column_names()
	if not cols:
		frappe.throw("tabSalesDashBoard does not exist on this site")

	if "id" not in cols:
		frappe.db.sql_ddl(
			f"ALTER TABLE `{TABLE}` ADD COLUMN `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY FIRST"
		)

	cols = _column_names()
	if "Company" not in cols:
		frappe.db.sql_ddl(f"ALTER TABLE `{TABLE}` ADD COLUMN `Company` VARCHAR(140) NULL")
	if "SI_Detail_Name" not in cols:
		frappe.db.sql_ddl(f"ALTER TABLE `{TABLE}` ADD COLUMN `SI_Detail_Name` VARCHAR(140) NULL")
	if "Bundle_Parent_Item" not in cols:
		frappe.db.sql_ddl(f"ALTER TABLE `{TABLE}` ADD COLUMN `Bundle_Parent_Item` VARCHAR(140) NOT NULL DEFAULT ''")
	if "PBI_Name" not in cols:
		frappe.db.sql_ddl(f"ALTER TABLE `{TABLE}` ADD COLUMN `PBI_Name` VARCHAR(140) NOT NULL DEFAULT ''")

	# Widen description if still capped at 140
	desc_row = frappe.db.sql(f"SHOW COLUMNS FROM `{TABLE}` LIKE 'Description'", as_dict=True)
	if desc_row and "varchar(140)" in (desc_row[0].get("Type") or "").lower():
		frappe.db.sql_ddl(f"ALTER TABLE `{TABLE}` MODIFY COLUMN `Description` VARCHAR(500) NULL")

	frappe.db.sql_ddl(
		f"CREATE INDEX IF NOT EXISTS `idx_sdb_date_territory` ON `{TABLE}` (`Invoice_Date`, `Territory`)"
	)
	frappe.db.sql_ddl(
		f"CREATE INDEX IF NOT EXISTS `idx_sdb_date_division` ON `{TABLE}` (`Invoice_Date`, `Division`)"
	)
	frappe.db.sql_ddl(
		f"CREATE INDEX IF NOT EXISTS `idx_sdb_date_subgroup` ON `{TABLE}` (`Invoice_Date`, `Sub_Group`(140))"
	)


def _run_sql_file(relative_path: str) -> None:
	app_path = frappe.get_app_path("erp_analysis")
	sql_path = os.path.join(app_path, "patches", "sql", relative_path)
	with open(sql_path, encoding="utf-8") as handle:
		sql = handle.read().strip()
	if not sql:
		frappe.throw(f"Empty SQL at {sql_path}")
	frappe.db.sql_ddl(sql)


def _create_view() -> None:
	_run_sql_file("view_printechs_bundle.sql")
	_run_sql_file("view_sales_dashboard_from_si.sql")


def _unique_index_exists() -> bool:
	rows = frappe.db.sql(
		f"SHOW INDEX FROM `{TABLE}` WHERE Key_name = %s",
		(UNIQUE_NAME,),
		as_dict=True,
	)
	return bool(rows)


def dedupe_sales_dashboard() -> int:
	"""Drop duplicate SDB rows (same business key), keep row with lowest ``id``."""
	cols = _column_names()
	if "id" not in cols:
		frappe.throw("tabSalesDashBoard.id column required for dedupe")

	before = frappe.db.sql(f"SELECT COUNT(*) FROM `{TABLE}`")[0][0]
	frappe.db.sql(
		f"""
		DELETE t1 FROM `{TABLE}` t1
		INNER JOIN `{TABLE}` t2 ON
			t1.`Invoice_No` = t2.`Invoice_No`
			AND COALESCE(t1.`SI_Detail_Name`, '') = COALESCE(t2.`SI_Detail_Name`, '')
			AND COALESCE(t1.`Item_Code`, '') = COALESCE(t2.`Item_Code`, '')
			AND COALESCE(t1.`Bundle_Parent_Item`, '') = COALESCE(t2.`Bundle_Parent_Item`, '')
			AND COALESCE(t1.`PBI_Name`, '') = COALESCE(t2.`PBI_Name`, '')
			AND COALESCE(t1.`Sales_Person`, '') = COALESCE(t2.`Sales_Person`, '')
			AND t1.`id` > t2.`id`
		"""
	)
	after = frappe.db.sql(f"SELECT COUNT(*) FROM `{TABLE}`")[0][0]
	return int(before - after)


def _add_unique_index() -> None:
	if _unique_index_exists():
		return
	dedupe_sales_dashboard()
	frappe.db.sql_ddl(
		f"""
		ALTER TABLE `{TABLE}`
		ADD UNIQUE KEY `{UNIQUE_NAME}` (
			`Invoice_No`(140),
			`SI_Detail_Name`(140),
			`Item_Code`(140),
			`Bundle_Parent_Item`(140),
			`PBI_Name`(140),
			`Sales_Person`(140)
		)
		"""
	)


def execute(refresh: bool = False):
	"""Patch entry: schema + view; optional full refresh (run regenerate_all separately)."""
	from erp_analysis.patches.ensure_sales_dashboard_table import ensure_sales_dashboard_table

	ensure = ensure_sales_dashboard_table(apply_view=True)
	if not ensure.get("ok"):
		return ensure

	_apply_schema()
	try:
		_create_view()
	except Exception:
		frappe.log_error(title="setup_sales_dashboard_from_si view", message=frappe.get_traceback())

	result = {"ok": True, "view": VIEW, "refreshed": False, "unique_index": False}

	if refresh:
		from frappeauth_app.tasks import regenerate_all

		msg = regenerate_all()
		result["refreshed"] = True
		result["refresh_message"] = msg

	try:
		_add_unique_index()
		result["unique_index"] = True
	except Exception:
		frappe.log_error(title="setup_sales_dashboard_from_si unique index", message=frappe.get_traceback())
		result["unique_index"] = False
		result["unique_index_note"] = "Run regenerate_all then re-run patch or add index manually"

	frappe.db.commit()
	return result


@frappe.whitelist()
def refresh_sales_dashboard():
	"""Re-apply SI view and full tabSalesDashBoard rebuild (bench execute)."""
	frappe.only_for("System Manager")
	_create_view()
	from frappeauth_app.tasks import regenerate_all

	msg = regenerate_all()
	try:
		_add_unique_index()
	except Exception:
		frappe.log_error(title="refresh_sales_dashboard unique index", message=frappe.get_traceback())
	frappe.db.commit()
	return {"ok": True, "message": msg}


def add_unique_index_after_dedupe():
	"""bench execute: dedupe then add uniq_sdb_invoice_line if missing."""
	removed = dedupe_sales_dashboard()
	_add_unique_index()
	frappe.db.commit()
	return {"ok": True, "rows_removed": removed, "unique_index": _unique_index_exists()}
