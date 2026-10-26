"""Mobile stock module — contract aliases for inventory drill-down APIs."""

from __future__ import annotations

from typing import Optional

import frappe


@frappe.whitelist()
def get_inventory_hierarchy(
	company: Optional[str] = None,
	warehouse: Optional[str] = None,
	level: str = "category",
	category: Optional[str] = None,
	item_group: Optional[str] = None,
	brand: Optional[str] = None,
	item_code: Optional[str] = None,
	territory: Optional[str] = None,
	territories: Optional[str] = None,
	limit: int = 100,
	**kwargs,
):
	"""Mobile path: erp_analysis.stock.get_inventory_hierarchy"""
	from erp_analysis.inventory import get_inventory_hierarchy as _impl

	return _impl(
		company=company,
		warehouse=warehouse,
		level=level,
		category=category,
		item_group=item_group,
		brand=brand,
		item_code=item_code,
		territory=territory or kwargs.get("territory"),
		territories=territories or kwargs.get("territories"),
		limit=limit if limit is not None else kwargs.get("limit", 100),
	)


@frappe.whitelist(methods=["GET", "POST"], allow_guest=False)
def get_item_stock_by_code(
	company: Optional[str] = None,
	item_code: Optional[str] = None,
	territory: Optional[str] = None,
	territories: Optional[str] = None,
	**kwargs,
):
	"""Mobile path: erp_analysis.stock.get_item_stock_by_code"""
	from erp_analysis.inventory import get_item_stock_by_code as _impl

	return _impl(
		company=company,
		item_code=item_code,
		territory=territory,
		territories=territories,
	)


@frappe.whitelist()
def get_inventory_items(
	company: Optional[str] = None,
	warehouse: Optional[str] = None,
	category: Optional[str] = None,
	item_group: Optional[str] = None,
	brand: Optional[str] = None,
	**kwargs,
):
	"""Mobile path: erp_analysis.stock.get_inventory_items"""
	from erp_analysis.inventory import get_inventory_items as _impl

	return _impl(
		company=company,
		warehouse=warehouse,
		category=category,
		item_group=item_group,
		brand=brand,
	)
