import frappe
from typing import Any

from erp_analysis import __version__ as APP_VERSION


@frappe.whitelist()
def probe_strict_empty_perm():
	"""Temporary desk diagnostic for Strict UP empty-link patch."""
	import frappe.permissions as perm_mod
	from erp_analysis.permissions import strict_empty_links as m

	m.ensure_strict_empty_link_patch()
	out = {
		"user": frappe.session.user,
		"strict": frappe.db.get_single_value("System Settings", "apply_strict_user_permissions"),
		"patched": m._patched,
		"fn": getattr(perm_mod.has_user_permission, "__qualname__", str(perm_mod.has_user_permission)),
		"results": {},
	}
	for dt in ("Sales Order", "Sales Invoice", "Delivery Note"):
		empty = frappe.new_doc(dt)
		jed = frappe.new_doc(dt)
		jed.territory = "Jeddah"
		riy = frappe.new_doc(dt)
		riy.territory = "Riyadh"
		out["results"][dt] = {
			"empty": bool(frappe.has_permission(dt, "create", doc=empty)),
			"jeddah": bool(frappe.has_permission(dt, "create", doc=jed)),
			"riyadh": bool(frappe.has_permission(dt, "create", doc=riy)),
		}
	return out


@frappe.whitelist(allow_guest=True)
def health():
	return {
		"ok": True,
		"status": "ok",
		"version": APP_VERSION,
		"message": "erp_analysis is available",
	}


@frappe.whitelist()
def get_mobile_config(**kwargs):
	from erp_analysis.utils.rpc import clean_kwargs
	from erp_analysis.mobile_config import get_mobile_config_cached

	clean_kwargs(kwargs)
	return get_mobile_config_cached()


@frappe.whitelist()
def get_mobile_bootstrap(company: str | None = None, **kwargs):
	"""Authenticated mobile bootstrap — profile, modules, dimensions, permissions."""
	from erp_analysis.utils.rpc import clean_kwargs
	from erp_analysis.services.mobile_bootstrap import build_mobile_bootstrap

	clean_kwargs(kwargs)
	return build_mobile_bootstrap(company=company)


@frappe.whitelist(methods=["GET", "POST"])
def get_dashboard_widget_data(
	widget_key: str | None = None,
	company: str | None = None,
	from_date: str | None = None,
	to_date: str | None = None,
	limit: int | None = None,
	dimension: str | None = None,
	filters: Any = None,
	drill_depth: int | None = None,
	compare: str | None = None,
	**kwargs,
):
	"""Return chart/list data for one profile dashboard widget (v2 dynamic home)."""
	from erp_analysis.services.mobile_widgets import get_dashboard_widget_data as _impl
	from erp_analysis.utils.rpc import clean_kwargs, get_arg, to_int

	clean_kwargs(kwargs)
	drill = get_arg("drill_depth", drill_depth)
	return _impl(
		widget_key=get_arg("widget_key", widget_key),
		company=get_arg("company", company),
		from_date=get_arg("from_date", from_date),
		to_date=get_arg("to_date", to_date),
		limit=to_int(get_arg("limit", limit), 10),
		dimension=get_arg("dimension", dimension),
		filters=get_arg("filters", filters),
		drill_depth=to_int(drill, None) if drill is not None and str(drill).strip() != "" else None,
		compare=get_arg("compare", compare),
		**kwargs,
	)


@frappe.whitelist(methods=["GET", "POST"])
def get_dashboard_board_data(
	dashboard_id: str | None = None,
	company: str | None = None,
	from_date: str | None = None,
	to_date: str | None = None,
	limit: int | None = None,
	use_cache: int | None = None,
	refresh: int | None = None,
	**kwargs,
):
	"""Return all widget payloads for one dashboard board (batch load)."""
	from erp_analysis.services.mobile_widgets import get_dashboard_board_data as _impl
	from erp_analysis.utils.rpc import clean_kwargs, get_arg, to_bool, to_int

	clean_kwargs(kwargs)
	return _impl(
		dashboard_id=get_arg("dashboard_id", dashboard_id),
		company=get_arg("company", company),
		from_date=get_arg("from_date", from_date),
		to_date=get_arg("to_date", to_date),
		limit=to_int(get_arg("limit", limit), 10),
		use_cache=to_bool(get_arg("use_cache", use_cache), True),
		refresh=to_bool(get_arg("refresh", refresh), False),
		**kwargs,
	)


@frappe.whitelist()
def get_my_access(user: str | None = None, company: str | None = None, **kwargs):
	from erp_analysis.utils.rpc import clean_kwargs

	clean_kwargs(kwargs)
	return _get_my_access(user=user, company=company)


@frappe.whitelist()
def clear_my_access_cache(user=None, **kwargs):
	from erp_analysis.utils.rpc import clean_kwargs

	clean_kwargs(kwargs)
	from erp_analysis.permissions.access_profile import clear_my_access_cache as _impl

	return _impl(user=user)


@frappe.whitelist(methods=["POST"])
def store_push_token(
	expo_token: str | None = None,
	platform: str | None = None,
	territory: str | None = None,
	company: str | None = None,
	user: str | None = None,
	**kwargs,
):
	from erp_analysis.utils.rpc import clean_kwargs

	payload = clean_kwargs(dict(kwargs))
	expo_token = expo_token or payload.get("expo_token")
	platform = platform or payload.get("platform")
	territory = territory or payload.get("territory")
	company = company or payload.get("company")
	user = user or payload.get("user")
	return _store_push_token(
		expo_token=expo_token,
		platform=platform,
		territory=territory,
		company=company,
		user=user,
	)


def _get_access_profile_by_user(user, company_filter=None):
	import os
	import socket

	try:
		meta_ap = frappe.get_meta("Access Profile")
	except Exception:
		return None

	candidate_fields: list[str] = []
	try:
		cols = frappe.db.sql("SHOW COLUMNS FROM `tabAccess Profile`", as_dict=True)
		existing_cols = {c["Field"] for c in cols}
	except Exception:
		existing_cols = set()

	for fieldname in ("user", "user_id", "owner"):
		if fieldname in existing_cols:
			candidate_fields.append(fieldname)

	for df in meta_ap.fields:
		if getattr(df, "options", None) == "User":
			if df.fieldname in existing_cols and df.fieldname not in candidate_fields:
				candidate_fields.append(df.fieldname)

	if not candidate_fields:
		return None

	for fieldname in candidate_fields:
		filters = {fieldname: user}
		if company_filter:
			filters["company"] = company_filter
		profile = frappe.db.get_value(
			"Access Profile",
			filters,
			["name", "company", "branch"],
			as_dict=True,
		)
		if profile:
			if fieldname != "user":
				try:
					host = socket.gethostname()
					pid = os.getpid()
					frappe.log_error(
						message=(
							f"Access Profile lookup used fallback column '{fieldname}' "
							f"for user '{user}' on {host} (pid {pid})"
						),
						title="Access Profile Fallback Lookup",
					)
				except Exception:
					pass
			return profile
	return None


def _get_my_access(user: str | None = None, company: str | None = None):
	"""Return Access Profile scope + object permissions for the logged-in user."""
	if not user:
		user = frappe.session.user

	profile = _get_access_profile_by_user(user, company_filter=company)
	if not profile:
		return {"scope": {}, "profiles": []}

	from erp_analysis.permissions.access_profile import (
		get_approve_territories,
		get_view_overrides,
		get_view_territories,
	)

	view_territories = get_view_territories(user=user, company=profile.company, expand=False) or []
	approve_territories = get_approve_territories(
		user=user, company=profile.company, expand=False
	)
	# Profile users always get a list (possibly empty / branch fallback)
	if approve_territories is None:
		approve_territories = []
	overrides = get_view_overrides(user, profile.company)

	legacy_territory = None
	try:
		meta = frappe.get_meta("Access Profile")
		if meta.has_field("territory"):
			legacy_territory = frappe.db.get_value("Access Profile", profile.name, "territory")
	except Exception:
		legacy_territory = None

	primary_territory = view_territories[0] if view_territories else legacy_territory

	scope = {
		"user": user,
		"company": profile.company,
		"branch": profile.branch,
		"territory": primary_territory,
		# Contract: territories aliases view_territories (backward compatible)
		"territories": list(view_territories),
		"view_territories": list(view_territories),
		"approve_territories": list(approve_territories),
		"allow_view_all_sales": overrides["allow_view_all_sales"],
		"allow_view_all_stock": overrides["allow_view_all_stock"],
		"allow_all_receivable": overrides["allow_all_receivable"],
	}

	try:
		meta_line = frappe.get_meta("Access Profile Line")
	except Exception:
		meta_line = None

	desired_fields = [
		"access_object",
		"object_type",
		"label",
		"can_view",
		"can_export",
		"can_create",
		"can_edit",
		"active",
		"sequence",
	]
	fetch_fields = [f for f in desired_fields if meta_line and meta_line.has_field(f)]
	if not fetch_fields:
		fetch_fields = ["access_object", "label"]

	order_by = "sequence" if (meta_line and meta_line.has_field("sequence")) else None

	lines = frappe.db.get_all(
		"Access Profile Line",
		filters={
			"parent": profile.name,
			"parenttype": "Access Profile",
			"parentfield": "access_rules",
		},
		fields=fetch_fields,
		order_by=order_by,
	)

	objects = []
	for row in lines:
		objects.append(
			{
				"object_key": row.get("access_object") or row.get("object_key"),
				"object_type": row.get("object_type"),
				"label": row.get("label"),
				"can_view": bool(row.get("can_view")) if "can_view" in row else False,
				"can_export": bool(row.get("can_export")) if "can_export" in row else False,
				"can_create": bool(row.get("can_create")) if "can_create" in row else False,
				"can_edit": bool(row.get("can_edit")) if "can_edit" in row else False,
				"active": bool(row.get("active")) if "active" in row else True,
			}
		)

	return {"scope": scope, "profiles": objects}


def _store_push_token(
	expo_token: str,
	platform: str | None = None,
	territory: str | None = None,
	company: str | None = None,
	user: str | None = None,
):
	"""Persist / refresh Expo push tokens for the logged-in user."""
	if not expo_token:
		frappe.throw("expo_token is required")

	if not user or user == "Guest":
		user = frappe.session.user
	if not user or user == "Guest":
		frappe.throw("Authentication required")

	platform_normalized = (platform or "").lower() or "ios"

	name = frappe.db.get_value("Mobile Push Token", {"expo_token": expo_token}, "name")
	if name:
		doc = frappe.get_doc("Mobile Push Token", name)
		doc.user = user
		doc.platform = platform_normalized
		if territory:
			doc.territory = territory
		if company:
			doc.company = company
		doc.last_seen = frappe.utils.now_datetime()
		doc.flags.ignore_mandatory = True
		doc.save(ignore_permissions=True)
	else:
		doc = frappe.get_doc(
			{
				"doctype": "Mobile Push Token",
				"user": user,
				"expo_token": expo_token,
				"platform": platform_normalized,
				"territory": territory,
				"company": company,
			}
		)
		doc.insert(ignore_permissions=True)

	frappe.db.commit()
	return {"ok": True, "name": doc.name}








