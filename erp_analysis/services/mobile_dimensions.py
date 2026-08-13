"""Metadata-driven mobile analysis dimensions (Phase B)."""

from __future__ import annotations

import json
from typing import Any, Optional

import frappe
from frappe import _

ALLOWED_SOURCE_DOCTYPES = frozenset(
	{
		"Item",
		"Customer",
		"Supplier",
		"Sales Invoice",
		"Sales Invoice Item",
		"Delivery Note",
		"Delivery Note Item",
		"Sales Order",
		"Sales Order Item",
		"Warehouse",
		"Territory",
		"Brand",
		"Item Group",
		"Customer Group",
		"Branch",
		"Cost Center",
		"Employee",
		"Sales Person",
	}
)

FORBIDDEN_FIELD_TYPES = frozenset(
	{
		"Password",
		"Attach",
		"Attach Image",
		"HTML",
		"Text Editor",
		"Markdown Editor",
		"Code",
		"JSON",
	}
)


def validate_dimension_definition(row: Any) -> None:
	"""Validate a Mobile Analysis Dimension row before save."""
	source_mode = (getattr(row, "source_mode", None) or "FIELD").strip().upper()
	if source_mode in ("DERIVED", "RELATION"):
		# Join paths validated in a later phase; require JSON when mode is set.
		if not (getattr(row, "join_path_json", None) or "").strip():
			frappe.throw(
				_("Join Path JSON is required for source mode {0}").format(source_mode)
			)
		return

	source_doctype = (getattr(row, "source_doctype", None) or "").strip()
	source_field = (getattr(row, "source_field", None) or "").strip()
	if not source_doctype or not source_field:
		frappe.throw(_("Source DocType and Source Field are required for FIELD/STANDARD modes"))

	if source_doctype not in ALLOWED_SOURCE_DOCTYPES:
		frappe.throw(_("Source DocType {0} is not allowed for mobile dimensions").format(source_doctype))

	meta = frappe.get_meta(source_doctype)
	df = meta.get_field(source_field)
	if not df:
		frappe.throw(_("Field {0} does not exist on {1}").format(source_field, source_doctype))

	if df.fieldtype in FORBIDDEN_FIELD_TYPES:
		frappe.throw(_("Field type {0} is not allowed for dimensions").format(df.fieldtype))

	if getattr(df, "hidden", 0) and not getattr(df, "in_list_view", 0):
		frappe.throw(_("Hidden/internal field {0} cannot be used as a dimension").format(source_field))


def get_profile_dimensions(profile_name: str, *, enabled_only: bool = True) -> list[dict[str, Any]]:
	"""Load dimension rows for a Mobile App Profile."""
	if not profile_name or not frappe.db.exists("Mobile App Profile", profile_name):
		return []

	profile = frappe.get_doc("Mobile App Profile", profile_name)
	rows = []
	for row in profile.dimensions or []:
		if enabled_only and not row.enabled:
			continue
		rows.append(row.as_dict())
	return rows


def resolve_dimension(profile_name: str, dimension_key: str) -> Optional[dict[str, Any]]:
	"""Map logical dimension_key to server-side field definition."""
	key = (dimension_key or "").strip().lower()
	if not key:
		return None

	for row in get_profile_dimensions(profile_name, enabled_only=True):
		if (row.get("dimension_key") or "").strip().lower() == key:
			return row
	return None


def dimension_public_metadata(row: dict[str, Any]) -> dict[str, Any]:
	"""Client-safe dimension metadata (no physical field names)."""
	data_type = row.get("data_type_override")
	if not data_type and row.get("source_doctype") and row.get("source_field"):
		try:
			meta = frappe.get_meta(row["source_doctype"])
			df = meta.get_field(row["source_field"])
			if df:
				data_type = df.fieldtype
		except Exception:
			pass

	return {
		"key": row.get("dimension_key"),
		"label": row.get("label") or row.get("dimension_key"),
		"data_type": data_type or "Data",
		"filterable": bool(row.get("allow_filter")),
		"groupable": bool(row.get("allow_group_by")),
		"sortable": bool(row.get("allow_sort")),
	}


def get_dimension_values(
	profile_name: str,
	dimension_key: str,
	search: Optional[str] = None,
	limit: int = 50,
) -> list[dict[str, Any]]:
	"""Return normalized label/value pairs for a configured dimension."""
	row = resolve_dimension(profile_name, dimension_key)
	if not row:
		frappe.throw(_("Unknown or disabled dimension: {0}").format(dimension_key), frappe.ValidationError)

	source_mode = (row.get("source_mode") or "FIELD").strip().upper()
	if source_mode in ("DERIVED", "RELATION"):
		frappe.throw(_("Dimension {0} is not yet supported for value lookup").format(dimension_key))

	source_doctype = row.get("source_doctype")
	source_field = row.get("source_field")
	meta = frappe.get_meta(source_doctype)
	df = meta.get_field(source_field)
	if not df:
		frappe.throw(_("Invalid dimension configuration for {0}").format(dimension_key))

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
	out = []
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


def parse_join_path(raw: str | None) -> Any:
	if not raw:
		return None
	try:
		return json.loads(raw)
	except Exception as exc:
		frappe.throw(_("Invalid Join Path JSON: {0}").format(exc))
