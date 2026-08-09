import frappe
from functools import lru_cache
from typing import Optional, Dict, List, Tuple, Union
from frappe.model.document import Document

PROFILE_DOCTYPE = "Access Profile"
PROFILE_LINE_DOCTYPE = "Access Profile Line"
PROFILE_TERRITORY_DOCTYPE = "Access Profile Territory"
REGISTRY_DOCTYPE = "Access Object Registry"


def clear_caches(
	doc: Optional[Document] = None,
	*_args,
	user: Optional[str] = None,
	**_kwargs,
):
	"""Clear cached permission helpers (accept doc or user)."""
	if doc and not user:
		user = getattr(doc, "user", None)
	elif doc and isinstance(doc, str) and not user:
		user = doc

	get_registry_map.cache_clear()
	get_profile.cache_clear()
	_get_territory_map.cache_clear()
	_get_approve_territory_map.cache_clear()
	_get_user_profile_name.cache_clear()
	get_view_overrides.cache_clear()
	if getattr(get_lines, "cache_clear", None):
		get_lines.cache_clear()
	if user:
		get_profile.cache_clear()
		_get_user_profile_name.cache_clear()
		get_view_overrides.cache_clear()


def clear_my_access_cache(user=None):
	"""Public helper for mobile/API cache busting."""
	clear_caches(user=user or frappe.session.user)
	return {"ok": True}


def on_user_logout(user: Optional[str] = None, **_kwargs):
	"""Hook helper to clear cached access scopes when a user logs out."""
	if user:
		clear_caches(user=user)


class PermissionDenied(frappe.PermissionError):
	pass


@lru_cache(maxsize=256)
def get_profile(
	user: str,
	company: str,
	territory: Optional[str] = None,
	branch: Optional[str] = None,
) -> Optional[dict]:
	"""Resolve the first Access Profile that matches the scope. Supports multi-territory assignments."""

	filters = {
		"user": user,
		"company": company,
		"enabled": 1,
		"docstatus": ["<", 2],
	}

	profiles = frappe.get_all(
		PROFILE_DOCTYPE,
		filters=filters,
		fields=["name", "branch"],
	)

	if not profiles:
		return None

	territory = territory or None
	branch = branch or None

	territory_map = _get_territory_map()

	for prof in profiles:
		if branch and prof.branch and prof.branch != branch:
			continue

		if territory:
			allowed_territories = territory_map.get(prof.name)
			if allowed_territories and territory not in allowed_territories:
				continue

		return prof
	return None


def get_lines(profile_name: str) -> List[dict]:
	return frappe.get_all(
		PROFILE_LINE_DOCTYPE,
		filters={"parent": profile_name, "parenttype": PROFILE_DOCTYPE, "active": 1},
		fields=[
			"access_object",
			"object_type",
			"can_view",
			"can_approve",
			"can_export",
			"can_create",
			"can_edit",
			"priority",
			"condition_expression",
			"data_filters_json",
		],
		order_by="priority asc, sequence asc",
	)


@lru_cache(maxsize=512)
def get_registry_map() -> Dict[str, dict]:
	registry = frappe.get_all(
		REGISTRY_DOCTYPE,
		filters={"is_active": 1},
		fields=["name", "object_type", "object_key"],
	)
	return {item.name: item for item in registry}


@lru_cache(maxsize=256)
def _get_territory_map() -> Dict[str, set[str]]:
	"""View territories: {profile_name: {territory, ...}} from parentfield=territories."""
	return _load_territory_map(parentfield="territories")


@lru_cache(maxsize=256)
def _get_approve_territory_map() -> Dict[str, set[str]]:
	"""Approve territories: {profile_name: {territory, ...}} from parentfield=approve_territories."""
	return _load_territory_map(parentfield="approve_territories")


def _load_territory_map(parentfield: str) -> Dict[str, set[str]]:
	rows = frappe.get_all(
		PROFILE_TERRITORY_DOCTYPE,
		filters={"parenttype": PROFILE_DOCTYPE, "parentfield": parentfield},
		fields=["parent", "territory"],
	)
	territory_map: Dict[str, set[str]] = {}
	for row in rows:
		if row.territory:
			territory_map.setdefault(row.parent, set()).add(row.territory)
	return territory_map


def evaluate(
	user: str, company: str, territory: Optional[str], branch: Optional[str], object_key: str
) -> dict:
	profile = get_profile(user, company, territory, branch)
	if not profile:
		raise PermissionDenied("No access profile found for this scope.")
	lines = get_lines(profile.name)
	registry_map = get_registry_map()

	for line in lines:
		registry_obj = registry_map.get(line.access_object)
		if not registry_obj:
			continue

		if registry_obj.object_key != object_key:
			continue

		decision = {
			"can_view": bool(line.can_view),
			"can_approve": bool(line.can_approve),
			"can_export": bool(getattr(line, "can_export", 0)),
			"can_create": bool(getattr(line, "can_create", 0)),
			"can_edit": bool(getattr(line, "can_edit", 0)),
			"data_filters": line.data_filters_json,
			"condition": line.condition_expression,
		}
		if not decision["can_view"] and not decision["can_approve"]:
			continue
		return decision

	raise PermissionDenied("No permission line matched for this object.")


@lru_cache(maxsize=512)
def _get_user_profile_name(user: str, company: Optional[str] = None) -> Optional[str]:
	"""Return enabled Access Profile name for user (company preferred, then any)."""
	if not user or user == "Guest":
		return None

	filters = {"user": user, "enabled": 1, "docstatus": ["<", 2]}
	if company:
		name = frappe.db.get_value(PROFILE_DOCTYPE, {**filters, "company": company}, "name")
		if name:
			return name

	return frappe.db.get_value(PROFILE_DOCTYPE, filters, "name")


def expand_territories(territories: Optional[List[str]]) -> List[str]:
	"""Include child territories (tree) for each selected territory."""
	if not territories:
		return []

	cleaned = [t for t in territories if t]
	if not cleaned:
		return []

	rows = frappe.db.sql(
		"""
		SELECT child.name
		FROM `tabTerritory` parent
		JOIN `tabTerritory` child
			ON child.lft >= parent.lft AND child.rgt <= parent.rgt
		WHERE parent.name IN %(territories)s
		""",
		{"territories": tuple(cleaned)},
		as_dict=True,
	)
	expanded = {row.name for row in rows if row.name}
	expanded.update(cleaned)
	return sorted(expanded)


def get_view_territories(
	user: Optional[str] = None,
	company: Optional[str] = None,
	*,
	expand: bool = True,
) -> Optional[List[str]]:
	"""
	Read/analytics territory scope (Access Profile → Territories / view_territories).

	Returns:
	  - list[str]: profile user with one or more view territories
	  - None: no Access Profile / no view territories → do not restrict
	"""
	user = user or frappe.session.user
	profile_name = _get_user_profile_name(user, company)
	if not profile_name:
		return None

	allowed = _get_territory_map().get(profile_name) or set()
	if not allowed:
		return None

	names = sorted(allowed)
	return expand_territories(names) if expand else names


def get_approve_territories(
	user: Optional[str] = None,
	company: Optional[str] = None,
	*,
	expand: bool = True,
) -> Optional[List[str]]:
	"""
	Approvals territory scope (Access Profile → Approve Territories).

	Returns:
	  - list[str]: profile user restricted to these territories for approve/list
	  - None: no Access Profile → do not apply profile approve restriction
	  - []: profile user with no approve territories and no branch fallback
	"""
	user = user or frappe.session.user
	profile_name = _get_user_profile_name(user, company)
	if not profile_name:
		return None

	explicit = _get_approve_territory_map().get(profile_name) or set()
	if explicit:
		names = sorted(explicit)
		return expand_territories(names) if expand else names

	# Contract fallback: Branch only (avoids accidental company-wide approve)
	branch = frappe.db.get_value(PROFILE_DOCTYPE, profile_name, "branch")
	if branch:
		names = [branch]
		return expand_territories(names) if expand else names

	return []


def get_allowed_territories(
	user: Optional[str] = None,
	company: Optional[str] = None,
	*,
	expand: bool = True,
) -> Optional[List[str]]:
	"""Backward-compatible alias for view/analytics territory scope."""
	return get_view_territories(user, company, expand=expand)


@lru_cache(maxsize=512)
def get_view_overrides(
	user: str,
	company: Optional[str] = None,
) -> Dict[str, bool]:
	"""Company-wide view override flags from Access Profile."""
	profile_name = _get_user_profile_name(user, company)
	empty = {
		"allow_view_all_sales": False,
		"allow_view_all_stock": False,
		"allow_all_receivable": False,
	}
	if not profile_name:
		return empty

	try:
		row = frappe.db.get_value(
			PROFILE_DOCTYPE,
			profile_name,
			["allow_view_all_sales", "allow_view_all_stock", "allow_all_receivable"],
			as_dict=True,
		)
	except Exception:
		return empty
	if not row:
		return empty
	return {
		"allow_view_all_sales": bool(row.get("allow_view_all_sales")),
		"allow_view_all_stock": bool(row.get("allow_view_all_stock")),
		"allow_all_receivable": bool(row.get("allow_all_receivable")),
	}


def bypass_view_territories(
	module: str,
	user: Optional[str] = None,
	company: Optional[str] = None,
) -> bool:
	"""
	True when Access Profile allows company-wide view for a module.

	module: sales | stock | receivables
	"""
	user = user or frappe.session.user
	flags = get_view_overrides(user, company)
	module = (module or "").strip().lower()
	if module == "sales":
		return flags["allow_view_all_sales"]
	if module in ("stock", "inventory"):
		return flags["allow_view_all_stock"]
	if module in ("receivables", "receivable", "ar"):
		return flags["allow_all_receivable"]
	return False


def resolve_territory_scope(
	requested: Optional[str] = None,
	requested_list: Optional[Union[str, List[str]]] = None,
	user: Optional[str] = None,
	company: Optional[str] = None,
	*,
	purpose: str = "view",
	module: Optional[str] = None,
) -> Optional[List[str]]:
	"""
	Resolve final territory filter for BA/approval queries.

	purpose:
	  - \"view\": executive / sales / GP / analytics (view_territories)
	  - \"approve\": approvals inbox + approve/reject (approve_territories)

	module (view only): sales | stock | receivables — when override flag is on,
	View Territories are ignored (company-wide unless client requests a filter).

	- Profile user: always scoped to the purpose set (unless module override).
	  Requested territory/territories must be within that set.
	- Non-profile user: filter only if a territory was explicitly requested;
	  otherwise None (no change / company-wide).
	"""
	user = user or frappe.session.user
	purpose = (purpose or "view").strip().lower()
	if purpose == "approve":
		allowed = get_approve_territories(user, company, expand=True)
	elif module and bypass_view_territories(module, user, company):
		# Override View Territories for this module
		allowed = None
	else:
		allowed = get_view_territories(user, company, expand=True)

	req: List[str] = []
	if requested_list:
		if isinstance(requested_list, str):
			req = [t.strip() for t in requested_list.split(",") if t and t.strip()]
		else:
			req = [str(t).strip() for t in requested_list if t and str(t).strip()]
	if requested and str(requested).strip():
		# single requested territory only if list not provided
		if not req:
			req = [str(requested).strip()]

	if allowed is None:
		return expand_territories(req) if req else None

	# Profile user with empty approve set → no documents in scope
	if purpose == "approve" and not allowed:
		return []

	allowed_set = set(allowed)
	if req:
		req_expanded = expand_territories(req)
		for terr in req_expanded:
			if terr not in allowed_set:
				frappe.throw(
					f"Access denied: territory '{terr}' is outside your Access Profile "
					f"{'approve' if purpose == 'approve' else 'view'} territories.",
					frappe.PermissionError,
				)
		return req_expanded

	return allowed


def assert_document_territory_allowed(
	doc_territory: Optional[str],
	user: Optional[str] = None,
	company: Optional[str] = None,
	*,
	purpose: str = "approve",
):
	"""Block access to a document outside the purpose territory set (default: approve)."""
	purpose = (purpose or "approve").strip().lower()
	if purpose == "approve":
		allowed = get_approve_territories(user, company, expand=True)
	else:
		allowed = get_view_territories(user, company, expand=True)
	if allowed is None:
		return
	if not allowed or not doc_territory or doc_territory not in set(allowed):
		frappe.throw(
			f"Access denied: document territory '{doc_territory or 'None'}' "
			f"is outside your Access Profile {purpose} territories.",
			frappe.PermissionError,
		)


def si_territory_sql(
	territories: Optional[List[str]],
	field: str = "si.territory",
) -> Tuple[str, List]:
	"""Return (sql_fragment, params) for Sales Invoice territory filtering."""
	if not territories:
		return "", []
	if len(territories) == 1:
		return f" AND {field} = %s ", [territories[0]]
	return f" AND {field} IN %s ", [tuple(territories)]


def get_allowed_warehouses(
	user: Optional[str] = None,
	company: Optional[str] = None,
) -> Optional[List[str]]:
	"""
	Warehouses in scope for Access Profile users (name contains an allowed territory).

	Returns:
	  - list[str]: restrict to these warehouses
	  - None: no Access Profile territory restriction / Allow View All Stock
	"""
	if bypass_view_territories("stock", user, company):
		return None

	territories = get_view_territories(user, company, expand=True)
	if territories is None:
		return None

	filters: Dict[str, object] = {"disabled": 0}
	if company:
		filters["company"] = company

	warehouses = frappe.get_all("Warehouse", filters=filters, pluck="name")
	if not warehouses:
		return []

	territory_lc = [t.lower() for t in territories if t]
	matched = [
		wh
		for wh in warehouses
		if any(t in (wh or "").lower() for t in territory_lc)
	]
	return matched


def resolve_warehouse_scope(
	requested: Optional[str] = None,
	user: Optional[str] = None,
	company: Optional[str] = None,
) -> Optional[List[str]]:
	"""
	Resolve warehouse filter for inventory queries.

	- Profile user: warehouses matching Access Profile territories.
	  Requested warehouse must be within that set.
	- Non-profile user: [requested] if provided, else None (no warehouse filter).
	"""
	allowed = get_allowed_warehouses(user, company)
	requested = (requested or "").strip() or None

	if allowed is None:
		return [requested] if requested else None

	allowed_set = set(allowed)
	if requested:
		if requested not in allowed_set:
			frappe.throw(
				f"Access denied: warehouse '{requested}' is outside your Access Profile territories.",
				frappe.PermissionError,
			)
		return [requested]

	return allowed


def warehouse_sql(
	warehouses: Optional[List[str]],
	field: str = "b.warehouse",
) -> Tuple[str, List]:
	"""Return (sql_fragment, params) for warehouse IN/EQ filtering."""
	if not warehouses:
		return "", []
	if len(warehouses) == 1:
		return f" AND {field} = %s ", [warehouses[0]]
	return f" AND {field} IN %s ", [tuple(warehouses)]
