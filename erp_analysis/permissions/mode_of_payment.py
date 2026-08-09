"""Mode of Payment visibility by Warehouse (+ Territory mapping).

Blank-warehouse MoPs (e.g. Wire Transfer) → all users.
Warehouse-set MoPs (city Cash/Cheques/Petty Cash, Alinma Wire Transfer) →
only users allowed for that warehouse via:
  - User Permission Warehouse applicable to Mode of Payment / all DocTypes
  - User Permission Territory matched to MoP warehouses by name
  - User.default_warehouse

Payment Entry dropdown also filters by user_default_warehouse (payment_entry_mop_query).

Requires Custom Field Mode of Payment.warehouse ignore_user_permissions=1
so Strict User Permissions does not hide blank-warehouse rows before this runs.
"""

from __future__ import annotations

import frappe

# System Managers / Administrator can manage the MoP master list & POS Profile.
# Branch users stay scoped. Payment Entry still filters by form warehouse in JS.
_OPEN_ROLES = frozenset({"System Manager"})

JEDDAH_OFFICE_WAREHOUSE = "Jeddah Office - WHS - PRNTX"
ALINMA_MOPS = ("Wire Transfer Alinma", "Wire Transfer Alinma Payroll")


def _user_has_open_access(user: str) -> bool:
	if user == "Administrator":
		return True
	return bool(set(frappe.get_roles(user)) & _OPEN_ROLES)


def _is_global_mop(warehouse: str | None) -> bool:
	"""Company-wide MoPs: blank warehouse only (not Alinma)."""
	return not (warehouse or "").strip()


def _global_mop_sql(alias: str = "`tabMode of Payment`") -> str:
	return f"(ifnull({alias}.warehouse, '') = '')"


def _warehouses_from_user_permission(user: str) -> set[str]:
	rows = frappe.get_all(
		"User Permission",
		filters={"user": user, "allow": "Warehouse"},
		fields=["for_value", "applicable_for", "apply_to_all_doctypes"],
	)
	out: set[str] = set()
	for row in rows:
		if row.get("apply_to_all_doctypes"):
			out.add(row.for_value)
			continue
		applicable = (row.get("applicable_for") or "").strip()
		if not applicable or applicable == "Mode of Payment":
			out.add(row.for_value)
	return out


def _warehouses_from_territory(user: str) -> set[str]:
	territories = {
		(t or "").strip()
		for t in frappe.get_all(
			"User Permission",
			filters={"user": user, "allow": "Territory"},
			pluck="for_value",
		)
		if t
	}
	if not territories:
		return set()

	mop_warehouses = frappe.db.sql_list(
		"""
		select distinct warehouse
		from `tabMode of Payment`
		where ifnull(warehouse, '') != ''
		"""
	)
	out: set[str] = set()
	for wh in mop_warehouses:
		wh_l = wh.lower()
		for territory in territories:
			if territory.lower() in wh_l:
				out.add(wh)
				break
	return out


def _warehouse_from_user_default(user: str) -> set[str]:
	wh = frappe.db.get_value("User", user, "default_warehouse")
	return {wh} if wh else set()


def get_allowed_mop_warehouses(user: str) -> list[str]:
	"""Warehouses that should scope Mode of Payment for this user."""
	return sorted(
		_warehouses_from_user_permission(user)
		| _warehouses_from_territory(user)
		| _warehouse_from_user_default(user)
	)


def get_permission_query_conditions(user: str | None = None) -> str | None:
	if not user:
		user = frappe.session.user
	if not user or user == "Guest":
		return "1=0"
	if _user_has_open_access(user):
		return None

	warehouses = get_allowed_mop_warehouses(user)
	global_mops = _global_mop_sql()
	if not warehouses:
		# No warehouse/territory scope → do not restrict (HQ / unscoped users)
		return None

	escaped = ", ".join(frappe.db.escape(w) for w in warehouses)
	return f"({global_mops} or `tabMode of Payment`.warehouse in ({escaped}))"


def has_permission(doc, ptype=None, user=None, debug=False):
	if not user:
		user = frappe.session.user
	if not user or user == "Guest":
		return False
	if _user_has_open_access(user):
		return None
	# Doctype-level checks pass a None/str — do not block those here
	if doc is None or isinstance(doc, str):
		return None

	warehouse = getattr(doc, "warehouse", None)
	if _is_global_mop(warehouse):
		return True

	allowed = get_allowed_mop_warehouses(user)
	if not allowed:
		return None
	return (warehouse or "").strip() in allowed


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def payment_entry_mop_query(doctype, txt, searchfield, start, page_len, filters):
	"""Link query: MoPs for PE warehouse + blank-warehouse (global Wire Transfer)."""
	warehouse = (filters or {}).get("warehouse")
	txt = (txt or "").strip()
	conds = ["ifnull(mop.enabled, 0) = 1"]
	values = {}

	if warehouse:
		conds.append("(ifnull(mop.warehouse, '') = '' or mop.warehouse = %(warehouse)s)")
		values["warehouse"] = warehouse

	if txt:
		conds.append(f"(mop.name like %(txt)s or mop.{searchfield} like %(txt)s)")
		values["txt"] = f"%{txt}%"

	where = " and ".join(conds)
	return frappe.db.sql(
		f"""
		select mop.name, mop.warehouse
		from `tabMode of Payment` mop
		where {where}
		order by mop.name
		limit %(start)s, %(page_len)s
		""",
		{**values, "start": start, "page_len": page_len},
	)


def ensure_alinma_jeddah_warehouse():
	"""Keep Alinma Wire Transfer MoPs scoped to Jeddah Office."""
	for name in ALINMA_MOPS:
		if not frappe.db.exists("Mode of Payment", name):
			continue
		current = frappe.db.get_value("Mode of Payment", name, "warehouse")
		if current != JEDDAH_OFFICE_WAREHOUSE:
			frappe.db.set_value(
				"Mode of Payment",
				name,
				"warehouse",
				JEDDAH_OFFICE_WAREHOUSE,
				update_modified=False,
			)
