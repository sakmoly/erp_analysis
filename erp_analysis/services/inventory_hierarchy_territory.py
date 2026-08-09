"""Territory-path inventory hierarchy (Bin valuation, name-based WH→territory).

Drill: territory → warehouse → brand → item_group → item

Warehouse ↔ Territory mapping (site1.local / printechs):
  No Warehouse.territory / branch custom field. Mapping is:
  territory name appears in Warehouse.name or parent_warehouse (case-insensitive).
  Unmapped warehouses are omitted (not shown as Unassigned).

Valuation: same as get_inventory_snapshot — qty × valuation_rate on tabBin.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import frappe
from frappe import _

from erp_analysis.permissions.access_profile import (
	resolve_territory_scope,
	resolve_warehouse_scope,
	warehouse_sql,
)

NO_BRAND = "No Brand"


def is_territory_path(
	level: str,
	*,
	territory: Optional[str] = None,
	category: Optional[str] = None,
	item_code: Optional[str] = None,
) -> bool:
	"""Parent-based router: Territory card vs Category card vs item leaf."""
	level = (level or "").strip().lower()
	territory = (territory or "").strip() or None
	category = (category or "").strip() or None
	item_code = (item_code or "").strip() or None

	# Existing Category-path leaf under item — not Territory card
	if item_code and level in ("warehouse", "territory"):
		return False
	# Category card wins when category parent is present
	if category:
		return False
	if level == "territory":
		return True
	if level == "warehouse" and territory:
		return True
	if level in ("brand", "item_group", "item") and territory:
		return True
	return False


def _company_currency(company: str) -> str:
	return frappe.get_cached_value("Company", company, "default_currency") or "SAR"


def _mapping_territories() -> List[str]:
	"""Territory masters used for name matching (longest first)."""
	names = frappe.get_all("Territory", filters={"is_group": 0}, pluck="name")
	if not names:
		names = frappe.get_all("Territory", pluck="name")
	# Drop generic roots that would false-match
	skip = {"all territories", "all territory"}
	names = [n for n in names if n and n.strip().lower() not in skip]
	return sorted(names, key=lambda n: len(n or ""), reverse=True)


def _territory_case_sql(alias: str = "w") -> Tuple[str, List[Any], List[str]]:
	"""
	SQL CASE mapping warehouse name/parent → territory.
	Returns (case_expr, case_params, territory_names_in_order).

	LIKE patterns use bind params so '%' is not eaten by Python/pymysql formatting.
	"""
	names = _mapping_territories()
	if not names:
		return "NULL", [], []

	parts: List[str] = []
	params: List[Any] = []
	hay = f"LOWER(CONCAT(IFNULL({alias}.name, ''), ' ', IFNULL({alias}.parent_warehouse, '')))"
	for name in names:
		parts.append(f"WHEN {hay} LIKE %s THEN %s")
		params.append(f"%{(name or '').lower()}%")
		params.append(name)
	return "CASE " + " ".join(parts) + " ELSE NULL END", params, names


def _resolve_scope(
	company: str,
	*,
	territory: Optional[str] = None,
	territories: Optional[str] = None,
	warehouse: Optional[str] = None,
) -> Tuple[Optional[List[str]], Optional[List[str]]]:
	"""
	Returns (allowed_territories, allowed_warehouses).
	None list = unrestricted for that dimension.
	"""
	terr_scope = resolve_territory_scope(
		requested=territory,
		requested_list=territories,
		company=company,
		purpose="view",
		module="stock",
	)
	wh_scope = resolve_warehouse_scope(requested=warehouse, company=company)
	return terr_scope, wh_scope


def _envelope(
	level: str,
	rows: List[Dict[str, Any]],
	*,
	company: str,
	total_value: float,
	has_more: bool = False,
	extra_meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
	meta: Dict[str, Any] = {
		"currency": _company_currency(company),
		"company": company,
		"total_value": float(total_value),
		"mapping": "warehouse name/parent contains territory name; unmapped omitted",
	}
	if has_more:
		meta["has_more"] = True
	if extra_meta:
		meta.update(extra_meta)
	return {"level": level, "rows": rows, "meta": meta}


def _pct(value: float, total: float) -> float:
	return round((value / total * 100.0), 2) if total > 0 else 0.0


def get_territory_hierarchy(
	*,
	company: str,
	level: str,
	territory: Optional[str] = None,
	territories: Optional[str] = None,
	warehouse: Optional[str] = None,
	brand: Optional[str] = None,
	item_group: Optional[str] = None,
	limit: int = 100,
) -> Dict[str, Any]:
	level = (level or "").strip().lower()
	territory = (territory or "").strip() or None
	warehouse = (warehouse or "").strip() or None
	brand = brand.strip() if isinstance(brand, str) else brand
	item_group = item_group.strip() if isinstance(item_group, str) else item_group
	limit = int(limit or 100)

	# Parent warehouse on brand+ is a drill filter, not the only allowed WH
	wh_requested = warehouse if level in ("brand", "item_group", "item") else None
	# For warehouse level under territory, don't pass warehouse as resolve requested
	terr_for_resolve = territory if level != "territory" else None
	terr_scope, wh_scope = _resolve_scope(
		company,
		territory=terr_for_resolve,
		territories=territories if level == "territory" else None,
		warehouse=wh_requested,
	)

	# Root territory: apply territories= chip via resolve (no single territory parent)
	if level == "territory":
		terr_scope, wh_scope = _resolve_scope(
			company,
			territory=None,
			territories=territories,
			warehouse=None,
		)

	# Empty warehouse scope = no stock visible
	if wh_scope is not None and len(wh_scope) == 0:
		return _envelope(level, [], company=company, total_value=0.0)

	if level == "territory":
		return _level_territory(company, terr_scope, wh_scope)
	if level == "warehouse":
		if not territory:
			frappe.throw(_("territory is required for level=warehouse"), frappe.ValidationError)
		return _level_warehouse(company, territory, terr_scope, wh_scope)
	if level == "brand":
		if not territory or not warehouse:
			frappe.throw(_("territory and warehouse are required for level=brand"), frappe.ValidationError)
		_assert_warehouse_in_territory(warehouse, territory)
		return _level_brand(company, territory, warehouse, wh_scope)
	if level == "item_group":
		if not territory or not warehouse or brand is None:
			frappe.throw(
				_("territory, warehouse and brand are required for level=item_group"),
				frappe.ValidationError,
			)
		_assert_warehouse_in_territory(warehouse, territory)
		return _level_item_group(company, territory, warehouse, brand, wh_scope)
	if level == "item":
		if not territory or not warehouse or brand is None or not item_group:
			frappe.throw(
				_("territory, warehouse, brand and item_group are required for level=item"),
				frappe.ValidationError,
			)
		_assert_warehouse_in_territory(warehouse, territory)
		return _level_item(company, territory, warehouse, brand, item_group, wh_scope, limit)

	frappe.throw(_("Invalid territory-path level: {0}").format(level), frappe.ValidationError)


def _assert_warehouse_in_territory(warehouse: str, territory: str):
	hay = (warehouse or "").lower()
	# Also check parent
	parent = frappe.db.get_value("Warehouse", warehouse, "parent_warehouse") or ""
	hay2 = f"{hay} {parent.lower()}"
	if territory.lower() not in hay2:
		frappe.throw(
			_("Warehouse '{0}' is not mapped to territory '{1}'").format(warehouse, territory),
			frappe.ValidationError,
		)


def _bin_base(
	company: str,
	wh_scope: Optional[List[str]],
	*,
	warehouse: Optional[str] = None,
) -> Tuple[str, List]:
	"""FROM/WHERE for Bin × Warehouse with company + scope. Value filter applied by caller."""
	where = ["w.company = %s", "b.actual_qty != 0"]
	params: List[Any] = [company]
	wh_sql, wh_params = warehouse_sql(wh_scope, field="b.warehouse")
	if wh_sql:
		where.append(wh_sql.replace(" AND ", "", 1).strip())
		params.extend(wh_params)
	if warehouse:
		where.append("b.warehouse = %s")
		params.append(warehouse)
	return " AND ".join(where), params


def _level_territory(
	company: str,
	terr_scope: Optional[List[str]],
	wh_scope: Optional[List[str]],
) -> Dict[str, Any]:
	case_sql, case_params, _ = _territory_case_sql("w")
	where_sql, where_params = _bin_base(company, wh_scope)
	# CASE placeholders appear before WHERE placeholders in the SQL text
	params: List[Any] = list(case_params) + list(where_params)

	query = f"""
		SELECT
			mapped.territory AS id,
			mapped.territory AS name,
			mapped.territory AS territory,
			SUM(mapped.line_value) AS value,
			SUM(mapped.qty) AS qty,
			COUNT(DISTINCT mapped.item_code) AS sku_count
		FROM (
			SELECT
				({case_sql}) AS territory,
				b.item_code,
				b.actual_qty AS qty,
				(b.actual_qty * COALESCE(b.valuation_rate, 0)) AS line_value
			FROM `tabBin` b
			INNER JOIN `tabWarehouse` w ON w.name = b.warehouse
			WHERE {where_sql}
		) mapped
		WHERE mapped.territory IS NOT NULL
		  AND mapped.line_value != 0
	"""
	if terr_scope is not None:
		if not terr_scope:
			return _envelope("territory", [], company=company, total_value=0.0)
		query += " AND mapped.territory IN %s"
		params.append(tuple(terr_scope))

	query += """
		GROUP BY mapped.territory
		HAVING SUM(mapped.line_value) > 0
		ORDER BY value DESC
	"""
	rows = frappe.db.sql(query, params, as_dict=True)
	total = sum(float(r.value or 0) for r in rows)
	out = []
	for r in rows:
		v = float(r.value or 0)
		out.append(
			{
				"id": r.id,
				"name": r.name,
				"territory": r.territory,
				"value": v,
				"stock_value": v,
				"qty": float(r.qty or 0),
				"percentage": _pct(v, total),
				"pct": _pct(v, total),
				"sku_count": int(r.sku_count or 0),
				"item_count": int(r.sku_count or 0),
			}
		)
	return _envelope("territory", out, company=company, total_value=total)


def _level_warehouse(
	company: str,
	territory: str,
	terr_scope: Optional[List[str]],
	wh_scope: Optional[List[str]],
) -> Dict[str, Any]:
	if terr_scope is not None and territory not in set(terr_scope):
		frappe.throw(
			_("Access denied: territory '{0}' is outside your stock view").format(territory),
			frappe.PermissionError,
		)

	case_sql, case_params, _ = _territory_case_sql("w")
	where_sql, where_params = _bin_base(company, wh_scope)
	params: List[Any] = list(case_params) + list(where_params) + [territory]

	query = f"""
		SELECT
			mapped.warehouse AS id,
			mapped.warehouse AS name,
			mapped.warehouse AS warehouse,
			SUM(mapped.line_value) AS value,
			SUM(mapped.qty) AS qty,
			COUNT(DISTINCT mapped.item_code) AS sku_count
		FROM (
			SELECT
				({case_sql}) AS territory,
				b.warehouse,
				b.item_code,
				b.actual_qty AS qty,
				(b.actual_qty * COALESCE(b.valuation_rate, 0)) AS line_value
			FROM `tabBin` b
			INNER JOIN `tabWarehouse` w ON w.name = b.warehouse
			WHERE {where_sql}
		) mapped
		WHERE mapped.territory = %s
		  AND mapped.line_value != 0
		GROUP BY mapped.warehouse
		HAVING SUM(mapped.line_value) > 0
		ORDER BY value DESC
	"""
	rows = frappe.db.sql(query, params, as_dict=True)
	total = sum(float(r.value or 0) for r in rows)
	out = []
	for r in rows:
		v = float(r.value or 0)
		out.append(
			{
				"id": r.id,
				"name": r.name,
				"warehouse": r.warehouse,
				"value": v,
				"stock_value": v,
				"qty": float(r.qty or 0),
				"percentage": _pct(v, total),
				"pct": _pct(v, total),
				"sku_count": int(r.sku_count or 0),
				"item_count": int(r.sku_count or 0),
			}
		)
	return _envelope("warehouse", out, company=company, total_value=total)


def _level_brand(
	company: str,
	territory: str,
	warehouse: str,
	wh_scope: Optional[List[str]],
) -> Dict[str, Any]:
	where_sql, params = _bin_base(company, wh_scope, warehouse=warehouse)
	query = f"""
		SELECT
			COALESCE(NULLIF(i.brand, ''), %s) AS id,
			COALESCE(NULLIF(i.brand, ''), %s) AS name,
			COALESCE(NULLIF(i.brand, ''), %s) AS brand,
			SUM(b.actual_qty * COALESCE(b.valuation_rate, 0)) AS value,
			SUM(b.actual_qty) AS qty
		FROM `tabBin` b
		INNER JOIN `tabWarehouse` w ON w.name = b.warehouse
		INNER JOIN `tabItem` i ON i.name = b.item_code
		WHERE {where_sql}
		GROUP BY COALESCE(NULLIF(i.brand, ''), %s)
		HAVING SUM(b.actual_qty * COALESCE(b.valuation_rate, 0)) > 0
		ORDER BY value DESC
	"""
	params = [NO_BRAND, NO_BRAND, NO_BRAND] + list(params) + [NO_BRAND]
	rows = frappe.db.sql(query, params, as_dict=True)
	total = sum(float(r.value or 0) for r in rows)
	out = []
	for r in rows:
		v = float(r.value or 0)
		out.append(
			{
				"id": r.id,
				"name": r.name,
				"brand": r.brand,
				"value": v,
				"stock_value": v,
				"qty": float(r.qty or 0),
				"percentage": _pct(v, total),
				"pct": _pct(v, total),
			}
		)
	return _envelope(
		"brand",
		out,
		company=company,
		total_value=total,
		extra_meta={"territory": territory, "warehouse": warehouse},
	)


def _level_item_group(
	company: str,
	territory: str,
	warehouse: str,
	brand: str,
	wh_scope: Optional[List[str]],
) -> Dict[str, Any]:
	where_sql, params = _bin_base(company, wh_scope, warehouse=warehouse)
	# Match Category card: prefer Item_type_name from view when present; else Item.item_group
	# Use Item.item_group for Bin path (stable); empty → Uncategorized
	brand_clause = "COALESCE(NULLIF(i.brand, ''), %s) = %s"
	query = f"""
		SELECT
			COALESCE(NULLIF(i.item_group, ''), 'Uncategorized') AS id,
			COALESCE(NULLIF(i.item_group, ''), 'Uncategorized') AS name,
			COALESCE(NULLIF(i.item_group, ''), 'Uncategorized') AS item_group,
			SUM(b.actual_qty * COALESCE(b.valuation_rate, 0)) AS value,
			SUM(b.actual_qty) AS qty
		FROM `tabBin` b
		INNER JOIN `tabWarehouse` w ON w.name = b.warehouse
		INNER JOIN `tabItem` i ON i.name = b.item_code
		WHERE {where_sql}
		  AND {brand_clause}
		GROUP BY COALESCE(NULLIF(i.item_group, ''), 'Uncategorized')
		HAVING SUM(b.actual_qty * COALESCE(b.valuation_rate, 0)) > 0
		ORDER BY value DESC
	"""
	params = list(params) + [NO_BRAND, brand]
	rows = frappe.db.sql(query, params, as_dict=True)
	total = sum(float(r.value or 0) for r in rows)
	out = []
	for r in rows:
		v = float(r.value or 0)
		out.append(
			{
				"id": r.id,
				"name": r.name,
				"item_group": r.item_group,
				"brand": brand,
				"value": v,
				"stock_value": v,
				"qty": float(r.qty or 0),
				"percentage": _pct(v, total),
				"pct": _pct(v, total),
			}
		)
	return _envelope(
		"item_group",
		out,
		company=company,
		total_value=total,
		extra_meta={"territory": territory, "warehouse": warehouse, "brand": brand},
	)


def _level_item(
	company: str,
	territory: str,
	warehouse: str,
	brand: str,
	item_group: str,
	wh_scope: Optional[List[str]],
	limit: int,
) -> Dict[str, Any]:
	where_sql, params = _bin_base(company, wh_scope, warehouse=warehouse)
	fetch = max(limit, 1) + 1
	query = f"""
		SELECT
			i.name AS id,
			i.item_name AS name,
			i.name AS item_code,
			i.item_name,
			i.stock_uom AS uom,
			SUM(b.actual_qty * COALESCE(b.valuation_rate, 0)) AS value,
			SUM(b.actual_qty) AS qty
		FROM `tabBin` b
		INNER JOIN `tabWarehouse` w ON w.name = b.warehouse
		INNER JOIN `tabItem` i ON i.name = b.item_code
		WHERE {where_sql}
		  AND COALESCE(NULLIF(i.brand, ''), %s) = %s
		  AND COALESCE(NULLIF(i.item_group, ''), 'Uncategorized') = %s
		GROUP BY i.name, i.item_name, i.stock_uom
		HAVING SUM(b.actual_qty * COALESCE(b.valuation_rate, 0)) > 0
		ORDER BY value DESC
		LIMIT %s
	"""
	params = list(params) + [NO_BRAND, brand, item_group, fetch]
	rows = frappe.db.sql(query, params, as_dict=True)
	has_more = len(rows) > limit
	rows = rows[:limit]
	total = sum(float(r.value or 0) for r in rows)
	out = []
	for r in rows:
		v = float(r.value or 0)
		q = float(r.qty or 0)
		out.append(
			{
				"id": r.id,
				"name": r.name or r.id,
				"item_code": r.item_code,
				"item_name": r.item_name,
				"value": v,
				"stock_value": v,
				"qty": q,
				"actual_qty": q,
				"uom": r.uom,
				"percentage": _pct(v, total),
				"pct": _pct(v, total),
			}
		)
	return _envelope(
		"item",
		out,
		company=company,
		total_value=total,
		has_more=has_more,
		extra_meta={
			"territory": territory,
			"warehouse": warehouse,
			"brand": brand,
			"item_group": item_group,
			"limit": limit,
		},
	)
