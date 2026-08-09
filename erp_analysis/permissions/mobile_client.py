"""Mobile-safe proxy for frappe.client.get_list / get and desk reportview."""

from __future__ import annotations

from typing import Any

import frappe

from erp_analysis.permissions.customer import (
	_company_for_user,
	_customer_get_list_kwargs,
	_parse_json_arg,
	_strip_client_only_kwargs,
	_user_has_customer_360_access,
)
from erp_analysis.utils.salesperson import resolve_salesperson_name, resolve_salesperson_names

_ORIGINAL_CLIENT_GET_LIST = frappe.client.get_list
_ORIGINAL_CLIENT_GET = frappe.client.get

SALES_PERFORMANCE_OBJECT_KEYS = frozenset(
	{
		"erp_analysis.sales_performance.get_salesperson_ranking",
		"erp_analysis.sales_performance.get_salesperson_performance",
		"erp_analysis.sales.get_salesperson_performance",
		"erp_analysis.sales_kpis.get_salesperson_performance",
	}
)

SALES_PERFORMANCE_DOCTYPES = frozenset({"Sales Invoice", "Sales Invoice Item"})


def _user_has_access(user: str | None, object_keys: frozenset[str]) -> bool:
	user = user or frappe.session.user
	if not user or user == "Guest":
		return False
	if user == "Administrator":
		return True

	from erp_analysis.permissions.access_profile import PermissionDenied, evaluate

	company = _company_for_user(user)
	if not company:
		return False

	for object_key in object_keys:
		try:
			decision = evaluate(user, company, None, None, object_key)
		except PermissionDenied:
			continue
		except Exception:
			frappe.log_error(title="mobile_client permission check", message=frappe.get_traceback())
			continue
		if decision.get("can_view"):
			return True
	return False


def _user_has_sales_performance_access(user: str | None = None) -> bool:
	return _user_has_access(user, SALES_PERFORMANCE_OBJECT_KEYS)


def _rewrite_salesperson_filters(filters: Any) -> Any:
	filters = _parse_json_arg(filters)
	if not filters:
		return filters

	if isinstance(filters, dict):
		rewritten = dict(filters)
		for key in ("sales_person", "Sales_Person"):
			if key in rewritten:
				value = rewritten[key]
				if isinstance(value, (list, tuple)) and value and str(value[0]).lower() == "in":
					rewritten[key] = ["in", resolve_salesperson_names(list(value[1:]))]
				else:
					rewritten[key] = resolve_salesperson_name(str(value))
		return rewritten

	if isinstance(filters, list):
		rewritten = []
		for row in filters:
			if not isinstance(row, (list, tuple)) or len(row) < 3:
				rewritten.append(row)
				continue

			doctype, fieldname, operator, *rest = row
			if fieldname in ("sales_person", "Sales_Person") or doctype == "Sales Team":
				if operator in ("=", "==", "like", "LIKE") and rest:
					rewritten.append([doctype, fieldname, operator, resolve_salesperson_name(str(rest[0]))])
				elif operator.lower() == "in" and rest:
					values = rest[0] if isinstance(rest[0], (list, tuple)) else rest
					rewritten.append([doctype, fieldname, operator, resolve_salesperson_names(list(values))])
				else:
					rewritten.append(row)
			else:
				rewritten.append(row)
		return rewritten

	return filters


def _sales_performance_get_list_kwargs(
	doctype: str,
	user: str,
	company: str | None,
	filters: Any = None,
	or_filters: Any = None,
	parent: str | None = None,
	**kwargs: Any,
) -> dict[str, Any]:
	list_kwargs = dict(kwargs)
	list_kwargs["filters"] = _rewrite_salesperson_filters(filters)
	list_kwargs["or_filters"] = or_filters
	list_kwargs["ignore_permissions"] = True
	if parent:
		list_kwargs["parent_doctype"] = parent

	if doctype == "Sales Invoice" and company:
		existing = list_kwargs["filters"] or []
		if isinstance(existing, dict):
			if not existing.get("company"):
				existing = dict(existing)
				existing["company"] = company
		elif isinstance(existing, list):
			has_company = any(
				isinstance(row, (list, tuple)) and len(row) >= 3 and row[0] in ("company", "Company")
				for row in existing
			)
			if not has_company:
				existing = list(existing)
				existing.append(["company", "=", company])
		list_kwargs["filters"] = existing

	return _strip_client_only_kwargs(list_kwargs)


def _get_doc_for_sales_performance(doctype: str, name=None, filters=None, parent=None):
	if name:
		doc = frappe.get_doc(doctype, name, ignore_permissions=True)
	elif filters or filters == {}:
		doc = frappe.get_doc(doctype, frappe.parse_json(filters), ignore_permissions=True)
	else:
		doc = frappe.get_doc(doctype, ignore_permissions=True)

	doc.apply_fieldlevel_read_permissions()
	return doc.as_dict()


@frappe.whitelist()
def client_get_list(
	doctype,
	fields=None,
	filters=None,
	group_by=None,
	order_by=None,
	limit_start=None,
	limit_page_length=20,
	parent=None,
	debug: bool = False,
	as_dict: bool = True,
	or_filters=None,
	expand=None,
):
	"""Route mobile get_list calls through Access Profile-aware handlers."""
	user = frappe.session.user
	company = _company_for_user(user)

	if doctype == "Customer" and _user_has_customer_360_access(user):
		list_kwargs = _customer_get_list_kwargs(
			user,
			company,
			filters=filters,
			or_filters=or_filters,
			fields=fields,
			group_by=group_by,
			order_by=order_by,
			limit_start=limit_start,
			limit_page_length=limit_page_length,
			parent=parent,
			debug=debug,
			as_dict=as_dict,
			expand=expand,
		)
		return frappe.get_list("Customer", **list_kwargs)

	# Sales Performance bypass is for mobile users who lack DocType read.
	# Desk users with normal read must keep User Permissions (Territory, etc.).
	if (
		doctype in SALES_PERFORMANCE_DOCTYPES
		and _user_has_sales_performance_access(user)
		and not frappe.has_permission(doctype, "read", user=user)
	):
		list_kwargs = _sales_performance_get_list_kwargs(
			doctype,
			user,
			company,
			filters=filters,
			or_filters=or_filters,
			parent=parent,
			fields=fields,
			group_by=group_by,
			order_by=order_by,
			limit_start=limit_start,
			limit_page_length=limit_page_length,
			debug=debug,
			as_dict=as_dict,
			expand=expand,
		)
		# Mobile path: still respect Access Profile view territories unless override
		list_kwargs = _apply_access_profile_view_territory(doctype, user, company, list_kwargs)
		return frappe.get_list(doctype, **list_kwargs)

	return _ORIGINAL_CLIENT_GET_LIST(
		doctype,
		fields=fields,
		filters=filters,
		group_by=group_by,
		order_by=order_by,
		limit_start=limit_start,
		limit_page_length=limit_page_length,
		parent=parent,
		debug=debug,
		as_dict=as_dict,
		or_filters=or_filters,
		expand=expand,
	)


@frappe.whitelist()
def client_get(doctype, name=None, filters=None, parent=None):
	"""Allow Sales Performance users to read invoice docs without DocType role perms."""
	user = frappe.session.user
	if (
		doctype in SALES_PERFORMANCE_DOCTYPES
		and _user_has_sales_performance_access(user)
		and not frappe.has_permission(doctype, "read", user=user)
	):
		doc = _get_doc_for_sales_performance(doctype, name=name, filters=filters, parent=parent)
		_assert_mobile_view_territory_for_doc(doctype, doc)
		return doc

	return _ORIGINAL_CLIENT_GET(doctype, name, filters, parent)


@frappe.whitelist()
@frappe.read_only()
def reportview_get():
	"""Allow Sales Performance users to use desk reportview on invoice doctypes."""
	from frappe.desk.reportview import compress, execute, get_form_params
	from frappe.model.utils import is_virtual_doctype
	from frappe.model.base_document import get_controller

	args = get_form_params()
	user = frappe.session.user
	# Desk list for users who already can read SI: never bypass User Permissions
	if (
		args.doctype in SALES_PERFORMANCE_DOCTYPES
		and _user_has_sales_performance_access(user)
		and not frappe.has_permission(args.doctype, "read", user=user)
	):
		if args.filters:
			args.filters = _rewrite_salesperson_filters(args.filters)
		args.filters = _inject_view_territory_filters(args.doctype, user, args.filters)
		if is_virtual_doctype(args.doctype):
			controller = get_controller(args.doctype)
			return compress(controller.get_list(args))
		return compress(execute(**args, ignore_permissions=True), args=args)

	from frappe.desk.reportview import get as original_reportview_get

	return original_reportview_get()


def _apply_access_profile_view_territory(
	doctype: str, user: str, company: str | None, list_kwargs: dict[str, Any]
) -> dict[str, Any]:
	"""For mobile ignore_permissions path, scope SI by Access Profile view territories."""
	if doctype != "Sales Invoice":
		return list_kwargs
	from erp_analysis.permissions.access_profile import resolve_territory_scope

	scope = resolve_territory_scope(company=company, purpose="view", module="sales")
	if not scope:
		return list_kwargs

	filters = list_kwargs.get("filters") or []
	if isinstance(filters, dict):
		filters = dict(filters)
		if "territory" not in filters:
			filters["territory"] = ["in", scope] if len(scope) > 1 else scope[0]
		list_kwargs["filters"] = filters
	elif isinstance(filters, list):
		has_terr = any(
			isinstance(row, (list, tuple)) and len(row) >= 2 and row[0] in ("territory", "Territory")
			for row in filters
		)
		if not has_terr:
			filters = list(filters)
			filters.append(
				["territory", "in", scope] if len(scope) > 1 else ["territory", "=", scope[0]]
			)
			list_kwargs["filters"] = filters
	return list_kwargs


def _inject_view_territory_filters(doctype: str, user: str, filters: Any) -> Any:
	company = _company_for_user(user)
	tmp = {"filters": filters or []}
	tmp = _apply_access_profile_view_territory(doctype, user, company, tmp)
	return tmp.get("filters")


def _assert_mobile_view_territory_for_doc(doctype: str, doc: dict[str, Any]):
	if doctype != "Sales Invoice":
		return
	from erp_analysis.permissions.access_profile import (
		assert_document_territory_allowed,
		bypass_view_territories,
	)

	company = doc.get("company") or _company_for_user()
	if bypass_view_territories("sales", company=company):
		return
	assert_document_territory_allowed(doc.get("territory"), company=company, purpose="view")
