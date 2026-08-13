"""Effective dimension resolution for analytics APIs (profile + legacy fallback)."""

from __future__ import annotations

import json
from typing import Any, Optional

import frappe
from frappe import _

from erp_analysis.mobile_config import DIMENSION_FIELDS, get_mobile_config_cached
from erp_analysis.permissions.access_profile import resolve_territory_scope
from erp_analysis.services.mobile_dimensions import (
	dimension_public_metadata,
	get_dimension_values as _profile_dimension_values,
	get_profile_dimensions,
	resolve_dimension,
)
from erp_analysis.services.mobile_profile import resolve_mobile_app_profile_name
from erp_analysis.utils.schema import has_field


def _first_field(doctype: str, candidates: tuple[str, ...]) -> Optional[str]:
	for fieldname in candidates:
		if has_field(doctype, fieldname):
			return fieldname
	return None


def _legacy_dimension_specs() -> dict[str, dict[str, Any]]:
	"""Built-in logical keys when no Mobile App Profile is linked."""
	specs: dict[str, dict[str, Any]] = {}

	def add(key: str, label: str, source_doctype: str, source_field: str):
		if not source_field:
			return
		specs[key] = {
			"dimension_key": key,
			"label": label,
			"enabled": 1,
			"source_doctype": source_doctype,
			"source_field": source_field,
			"source_mode": "FIELD",
			"analysis_doctype": source_doctype,
			"analysis_field": source_field,
			"allow_filter": 1,
			"allow_group_by": 1,
			"allow_sort": 0,
		}

	add("company", "Company", "Sales Invoice", "company")
	add("territory", "Territory", "Sales Invoice", "territory")
	add("brand", "Brand", "Sales Invoice Item", "brand")
	add("warehouse", "Warehouse", "Sales Invoice", _first_field("Sales Invoice", ("set_warehouse", "warehouse")) or "")
	if "warehouse" not in specs:
		add("warehouse", "Warehouse", "Sales Invoice Item", _first_field("Sales Invoice Item", ("warehouse",)) or "")

	division = _first_field("Sales Invoice", ("custom_division", "division"))
	add("division", "Division", "Sales Invoice", division or "")
	department = _first_field("Sales Invoice", ("custom_department", "department"))
	add("department", "Department", "Sales Invoice", department or "")
	cost_center = _first_field("Sales Invoice", ("cost_center", "custom_cost_center"))
	add("cost_center", "Cost Center", "Sales Invoice", cost_center or "")
	branch = _first_field("Sales Invoice", ("branch", "custom_branch"))
	add("branch", "Branch", "Sales Invoice", branch or "")

	return {k: v for k, v in specs.items() if v.get("source_field")}


def list_effective_dimensions(user: str, company: Optional[str] = None) -> list[dict[str, Any]]:
	profile_name = resolve_mobile_app_profile_name(user=user, company=company)
	if profile_name:
		return [
			dimension_public_metadata(row)
			for row in get_profile_dimensions(profile_name, enabled_only=True)
		]

	config = get_mobile_config_cached()
	enabled = config.get("dimensions") or {}
	specs = _legacy_dimension_specs()
	out: list[dict[str, Any]] = []
	for key in DIMENSION_FIELDS:
		if not enabled.get(key, False):
			continue
		spec = specs.get(key)
		if spec:
			out.append(dimension_public_metadata(spec))
	return out


def resolve_effective_dimension(
	user: str,
	company: Optional[str],
	dimension_key: str,
) -> dict[str, Any]:
	key = (dimension_key or "").strip().lower()
	if not key:
		frappe.throw(_("Dimension is required"), frappe.ValidationError)

	profile_name = resolve_mobile_app_profile_name(user=user, company=company)
	if profile_name:
		row = resolve_dimension(profile_name, key)
		if not row:
			frappe.throw(_("Unknown or disabled dimension: {0}").format(dimension_key), frappe.ValidationError)
		return _normalize_analysis_row(row)

	config = get_mobile_config_cached()
	if not (config.get("dimensions") or {}).get(key, False):
		frappe.throw(_("Unknown or disabled dimension: {0}").format(dimension_key), frappe.ValidationError)

	spec = _legacy_dimension_specs().get(key)
	if not spec:
		frappe.throw(_("Dimension {0} is not configured on this site").format(dimension_key), frappe.ValidationError)
	return _normalize_analysis_row(spec)


def _normalize_analysis_row(row: dict[str, Any]) -> dict[str, Any]:
	analysis_doctype = row.get("analysis_doctype") or row.get("source_doctype")
	analysis_field = row.get("analysis_field") or row.get("source_field")
	if not analysis_doctype or not analysis_field:
		frappe.throw(_("Invalid dimension configuration for {0}").format(row.get("dimension_key")))
	if not has_field(analysis_doctype, analysis_field):
		frappe.throw(_("Dimension field missing on site: {0}").format(row.get("dimension_key")))
	out = dict(row)
	out["analysis_doctype"] = analysis_doctype
	out["analysis_field"] = analysis_field
	out["sql_alias"] = "si" if analysis_doctype == "Sales Invoice" else "sii"
	return out


def parse_logical_filters(raw: Any) -> dict[str, list[Any]]:
	if raw is None or raw == "":
		return {}
	if isinstance(raw, str):
		try:
			raw = json.loads(raw)
		except Exception as exc:
			frappe.throw(_("Invalid filters JSON: {0}").format(exc))
	if not isinstance(raw, dict):
		frappe.throw(_("filters must be a JSON object"))
	out: dict[str, list[Any]] = {}
	for key, values in raw.items():
		if values is None:
			continue
		if not isinstance(values, (list, tuple)):
			values = [values]
		out[(key or "").strip().lower()] = list(values)
	return out


def validate_logical_filters(
	user: str,
	company: Optional[str],
	filters: dict[str, list[Any]],
) -> list[tuple[dict[str, Any], list[Any]]]:
	validated: list[tuple[dict[str, Any], list[Any]]] = []
	for dim_key, values in (filters or {}).items():
		if not values:
			continue
		row = resolve_effective_dimension(user, company, dim_key)
		if not row.get("allow_filter"):
			frappe.throw(_("Dimension {0} is not filterable").format(dim_key), frappe.ValidationError)
		_validate_filter_scope(user, company, dim_key, values)
		validated.append((row, values))
	return validated


def _validate_filter_scope(
	user: str,
	company: Optional[str],
	dimension_key: str,
	values: list[Any],
) -> None:
	"""Reject filter values outside Access Profile company / territory scope."""
	key = (dimension_key or "").strip().lower()
	if key == "territory":
		resolve_territory_scope(
			requested_list=[str(v) for v in values if v is not None and str(v).strip()],
			user=user,
			company=company,
			purpose="view",
			module="sales",
		)
	elif key == "company" and company:
		for value in values:
			if str(value) != company:
				frappe.throw(
					_("Company {0} is outside your access scope").format(value),
					frappe.PermissionError,
				)


def get_effective_dimension_values(
	user: str,
	company: Optional[str],
	dimension_key: str,
	search: Optional[str] = None,
	limit: int = 50,
) -> list[dict[str, Any]]:
	profile_name = resolve_mobile_app_profile_name(user=user, company=company)
	row = resolve_effective_dimension(user, company, dimension_key)

	if profile_name and resolve_dimension(profile_name, dimension_key):
		values = _profile_dimension_values(profile_name, dimension_key, search=search, limit=limit)
	else:
		values = _legacy_dimension_values(row, search=search, limit=limit)

	key = (dimension_key or "").strip().lower()
	if key == "territory":
		values = _apply_territory_scope_to_values(user, company, values)
	elif key == "company" and company:
		values = [v for v in values if str(v.get("value")) == company]

	return values


def _legacy_dimension_values(
	row: dict[str, Any],
	search: Optional[str] = None,
	limit: int = 50,
) -> list[dict[str, Any]]:
	source_doctype = row["source_doctype"]
	source_field = row["source_field"]
	meta = frappe.get_meta(source_doctype)
	df = meta.get_field(source_field)
	if not df:
		frappe.throw(_("Invalid dimension configuration for {0}").format(row.get("dimension_key")))

	limit = max(1, min(int(limit or 50), 200))
	filters: dict[str, Any] = {}
	if search and df.fieldtype in ("Link", "Data", "Select"):
		filters[source_field] = ["like", f"%{search.strip()}%"]

	if df.fieldtype == "Link":
		values = frappe.get_all(
			source_doctype,
			filters=filters or None,
			pluck=source_field,
			distinct=True,
			limit_page_length=limit,
			order_by=f"{source_field} asc",
		)
		return [{"value": v, "label": v} for v in values if v]

	values = frappe.get_all(
		source_doctype,
		filters=filters or None,
		fields=[source_field],
		distinct=True,
		limit_page_length=limit,
	)
	out: list[dict[str, Any]] = []
	seen: set[str] = set()
	for item in values:
		val = item.get(source_field)
		if val is None or str(val) in seen:
			continue
		seen.add(str(val))
		out.append({"value": val, "label": str(val)})
		if len(out) >= limit:
			break
	return out


def _apply_territory_scope_to_values(
	user: str,
	company: Optional[str],
	values: list[dict[str, Any]],
) -> list[dict[str, Any]]:
	scope = resolve_territory_scope(company=company, purpose="view", module="sales")
	if scope is None:
		return values
	allowed = set(scope)
	return [v for v in values if v.get("value") in allowed]
