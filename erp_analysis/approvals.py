# erp_analysis/api/approvals.py
import frappe
from frappe import _
from frappe.utils import nowdate, getdate, add_months, cint, flt
from typing import Optional, Dict, Any, List
from erp_analysis.permissions.access_profile import (
    evaluate,
    PermissionDenied,
    get_profile,
    _get_territory_map,
    resolve_territory_scope,
    assert_document_territory_allowed,
)
from frappe.model.meta import get_meta

OBJECT_KEY_BY_DOCTYPE = {
    "Sales Invoice": "erp_analysis.approvals.sales_invoice",
    "Delivery Note": "erp_analysis.approvals.delivery_note",
}


@frappe.whitelist(methods=["POST"])
def approve_document(
    doctype: Optional[str] = None,
    docname: Optional[str] = None,
    action: Optional[str] = None,
    workflow_action: Optional[str] = None,
    comments: Optional[str] = None,
    company: Optional[str] = None,
    territory: Optional[str] = None,
    branch: Optional[str] = None,
) -> Dict[str, Any]:
    """Approve (or otherwise transition) a pending document via workflow or submission."""

    if frappe.session.user == "Guest":
        try:
            # Log incoming request for debugging: user, presence of Authorization header,
            # a short roles snapshot, and header keys (do not log header values or tokens).
            req = getattr(frappe.local, "request", None)
            headers_keys = []
            auth_present = False
            if req is not None:
                try:
                    hdrs = dict(getattr(req, "headers", {}) or {})
                    headers_keys = list(hdrs.keys())[:20]
                    # Check for Authorization existence without logging its value
                    auth_present = any(k.lower() == "authorization" for k in hdrs.keys())
                except Exception:
                    headers_keys = []
                    auth_present = False
            try:
                roles = frappe.get_roles() or []
            except Exception:
                roles = []
            frappe.log_error(
                title="approve_document request incoming",
                message=(
                    f"user={frappe.session.user}, auth_present={auth_present}, "
                    f"roles={roles[:5]}, headers_keys={headers_keys}"
                ),
            )
        except Exception:
            pass
        frappe.throw("Authentication required", frappe.PermissionError)

    payload = frappe._dict(frappe.form_dict or {})

    doctype = (doctype or payload.get("doctype") or payload.get("doc_type") or "").strip()
    docname = docname or payload.get("docname") or payload.get("name") or payload.get("doc_name")
    if not doctype:
        frappe.throw("Parameter 'doctype' is required.", frappe.ValidationError)
    if not docname:
        frappe.throw("Parameter 'docname' (or 'name') is required.", frappe.ValidationError)

    workflow_action = (
        workflow_action
        or payload.get("workflow_action")
        or payload.get("workflowAction")
        or payload.get("transition")
    )
    action = (
        action
        or payload.get("action")
        or payload.get("workflow_state_action")
        or payload.get("next_action")
    )
    comments = comments or payload.get("comments") or payload.get("remark") or payload.get("remarks")
    company = (company or payload.get("company") or "").strip()
    territory = (territory or payload.get("territory") or "").strip()
    branch = (branch or payload.get("branch") or "").strip()

    doc = frappe.get_doc(doctype, docname)

    doc_company = company or getattr(doc, "company", None) or ""
    doc_territory = territory or getattr(doc, "territory", None) or ""
    doc_branch = branch or getattr(doc, "branch", None) or ""
    if not branch:
        branch = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "branch") or ""
    branch = branch.strip()
    doc_branch = (doc_branch or "").strip()

    # Profile users: document territory must be inside approve_territories
    assert_document_territory_allowed(
        getattr(doc, "territory", None), company=doc_company, purpose="approve"
    )

    object_key = OBJECT_KEY_BY_DOCTYPE.get(doctype)
    if not object_key:
        object_key = f"erp_analysis.approvals.{frappe.scrub(doctype)}"

    from erp_analysis.permissions.access_profile import get_approve_territories

    allowed = get_approve_territories(company=doc_company)
    territory_candidates: List[Optional[str]] = []
    for value in [doc_territory, territory]:
        if value and str(value).strip():
            value = str(value).strip()
            if allowed is not None and value not in set(allowed):
                continue
            if value not in territory_candidates:
                territory_candidates.append(value)
    # Non-profile users keep loose None candidate; profile users stay within allowed only
    if allowed is None and None not in territory_candidates:
        territory_candidates.append(None)
    if not territory_candidates and allowed:
        territory_candidates = list(allowed[:1])

    branch_candidates: List[Optional[str]] = []
    for value in [doc_branch, branch, "", None]:
        candidate = (value or "").strip()
        if candidate and candidate not in branch_candidates:
            branch_candidates.append(candidate)
    if None not in branch_candidates:
        branch_candidates.append(None)

    decision: Optional[Dict[str, Any]] = None
    last_error: Optional[str] = None
    for terr in territory_candidates or [None]:
        for br in branch_candidates or [None]:
            try:
                decision = evaluate(
                    frappe.session.user,
                    doc_company,
                    terr or None,
                    br or None,
                    object_key,
                )
                break
            except PermissionDenied:
                last_error = frappe.get_traceback()
                continue
        if decision:
            break

    if not decision:
        if last_error:
            frappe.log_error(
                title="approve_document permission failure",
                message=(
                    f"doctype={doctype}, name={docname}, company={doc_company}, territory={doc_territory}, "
                    f"branch={branch}, object_key={object_key}\n{last_error}"
                ),
            )
        frappe.throw(
            f"You do not have approval access for {doctype} {docname}.",
            frappe.PermissionError,
        )

    if not decision.get("can_approve"):
        frappe.throw(
            f"You do not have approval access for {doctype} {docname}.",
            frappe.PermissionError,
        )

    workflow_applied = False

    workflow_name = frappe.model.workflow.get_workflow_name(doctype)
    desired_action = workflow_action or action
    if workflow_name:
        transitions: List[Dict[str, Any]] = []
        try:
            transitions = frappe.model.workflow.get_transitions(doc, raise_exception=False)
        except Exception:
            frappe.log_error(
                title="approve_document transitions error",
                message=f"doctype={doctype}, name={docname}\n{frappe.get_traceback()}",
            )
        if not desired_action and len(transitions) == 1:
            desired_action = transitions[0].get("action")
        if not desired_action:
            for transition in transitions:
                if transition.get("action", "").lower() == "approve":
                    desired_action = transition.get("action")
                    break
        if desired_action:
            try:
                frappe.model.workflow.apply_workflow(doc, desired_action)
                workflow_applied = True
            except Exception:
                frappe.log_error(
                    title="approve_document workflow error",
                    message=(
                        f"doctype={doctype}, name={docname}, action={desired_action}\n"
                        f"{frappe.get_traceback()}"
                    ),
                )
                if workflow_action:
                    raise

    if not workflow_applied:
        if doc.meta.is_submittable and doc.docstatus == 0:
            doc.submit()
        else:
            doc.save()

    if comments:
        doc.add_comment("Comment", comments)

    frappe.db.commit()

    doc.reload()

    return {
        "message": {
            "status": "success",
            "doctype": doc.doctype,
            "name": doc.name,
            "docstatus": doc.docstatus,
            "workflow_state": getattr(doc, "workflow_state", None),
            "workflow_applied": workflow_applied,
            "workflow_action": desired_action if workflow_applied else None,
        }
    }


@frappe.whitelist(methods=["GET", "POST"], allow_guest=False)
def get_all_approvals(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    company: Optional[str] = None,
    territory: Optional[str] = None,
    doctypes: Optional[str] = None,
    limit: Optional[int] = 100,
    territories: Optional[str] = None,
    workflow_states: Optional[str] = None,
) -> Dict[str, Any]:
    """Return approval records for Sales Invoice and Delivery Note only."""

    company_filter = (company or "").strip()
    user_default_company = frappe.defaults.get_user_default("Company") or ""
    perm_company = (company_filter or user_default_company).strip()
    if not perm_company:
        perm_company = _resolve_company_from_access_profile(frappe.session.user) or ""
    if not perm_company:
        frappe.throw("Set a default Company or pass ?company=... for approvals.", frappe.ValidationError)

    territory = (territory or frappe.defaults.get_user_default("Territory") or "").strip()
    # Branch is intentionally ignored for approvals visibility: access is managed via territories.
    branch = ""

    territories_param = territories or frappe.form_dict.get("territories")
    # Profile users → approve_territories only (never full view list).
    territory_filters = resolve_territory_scope(
        requested=territory or None,
        requested_list=territories_param,
        company=perm_company,
        purpose="approve",
    )

    states_param = workflow_states or frappe.form_dict.get("workflow_states")
    if states_param:
        delivery_states = [
            s.strip()
            for s in states_param.split(",")
            if isinstance(s, str) and s.strip()
        ]
    else:
        delivery_states = ["Approved By Finance Coordinator"]

    def _check(object_key: str) -> bool:
        # Allow Administrator and System Manager to bypass access checks
        if frappe.session.user == "Administrator" or "System Manager" in frappe.get_roles():
            return True

        territory_candidates: List[str] = []
        if territory_filters:
            territory_candidates.extend(territory_filters)
        elif territory:
            territory_candidates.append(territory)
        else:
            # Non-profile users: allow evaluate without territory constraint
            territory_candidates.append("")

        for terr in territory_candidates:
            try:
                decision = evaluate(
                    frappe.session.user,
                    perm_company,
                    terr or None,
                    None,
                    object_key,
                )
                if decision.get("can_view") or decision.get("can_approve"):
                    return True
            except PermissionDenied:
                continue
        return False
   
    if not from_date:
        from_date = add_months(nowdate(), -2)
    if not to_date:
        to_date = nowdate()

    from_date = str(getdate(from_date)) if from_date else None
    to_date = str(getdate(to_date)) if to_date else None
    limit = cint(limit) or 100

    wanted_doctypes = set(
        dt.strip()
        for dt in (doctypes.split(",") if doctypes else [])
        if dt.strip()
    ) or {"Sales Invoice", "Delivery Note"}

    approvals: List[Dict[str, Any]] = []

    if "Sales Invoice" in wanted_doctypes and _check("erp_analysis.approvals.sales_invoice"):
        approvals.extend(
            _fetch_sales_invoices(
                from_date, to_date, company_filter, territory_filters, limit
            )
        )

    if "Delivery Note" in wanted_doctypes and _check("erp_analysis.approvals.delivery_note"):
        approvals.extend(
            _fetch_delivery_notes(
                from_date,
                to_date,
                company_filter,
                territory_filters,
                limit,
                delivery_states or None,
            )
        )

    # aging calculation
    pairs = {
        (r.get("customer"), r.get("company"))
        for r in approvals
        if r.get("customer") and r.get("company")
    }
    cache_outstanding: Dict[tuple, Dict[str, float]] = {}
    for cust, comp in pairs:
        cache_outstanding[(cust, comp)] = _compute_customer_aging(cust, comp)

    for row in approvals:
        cust, comp = row.get("customer"), row.get("company")
        aging = cache_outstanding.get((cust, comp), {}) if cust and comp else {}
        row["customer_outstanding"] = flt(aging.get("total_outstanding", 0))
        row["customer_overdue"] = flt(aging.get("overdue_total", 0))
        row["outstanding_0_30"] = flt(aging.get("b0_30", 0))
        row["outstanding_31_60"] = flt(aging.get("b31_60", 0))
        row["outstanding_61_90"] = flt(aging.get("b61_90", 0))
        row["outstanding_over_90"] = flt(aging.get("b_over_90", 0))

    counts = {
        "sales_invoices": sum(1 for r in approvals if r.get("doctype") == "Sales Invoice"),
        "delivery_notes": sum(1 for r in approvals if r.get("doctype") == "Delivery Note"),
        "material_requests": 0,  # kept key for compatibility
    }
    total_pending = len(approvals)

    return {
        "message": {
            "approvals": approvals,
            "total_pending": total_pending,
            **counts,
        }
    }
    
    
# ----------------------- Fetchers -----------------------
def _expand_territories(territories: Optional[List[str]]) -> List[str]:
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


def _fetch_sales_invoices(from_date, to_date, company, territories, limit):
    conds, vals = ["si.docstatus = 0"], {}
    conds.append("(si.status IS NULL OR si.status = 'Draft')")

    if from_date and to_date:
        conds.append("si.posting_date BETWEEN %(from)s AND %(to)s")
        vals.update({"from": from_date, "to": to_date})
    elif from_date:
        conds.append("si.posting_date >= %(from)s")
        vals["from"] = from_date
    elif to_date:
        conds.append("si.posting_date <= %(to)s")
        vals["to"] = to_date

    if company:
        conds.append("si.company = %(company)s")
        vals["company"] = company
    ...
    if territories:
        cleaned = _expand_territories(territories)
        if cleaned:
            if len(cleaned) == 1:
                conds.append("si.territory = %(territory)s")
                vals["territory"] = cleaned[0]
            else:
                conds.append("si.territory IN %(territories)s")
                vals["territories"] = tuple(cleaned)

    rows = frappe.db.sql(
        f"""
        SELECT
            si.name,
            si.customer_name,
            si.customer,
            si.posting_date,
            si.company,
            si.territory,
            COALESCE(si.total_qty, 0)                     AS total_quantity,
            COALESCE(si.base_net_total, 0)                 AS total_amount,
            COALESCE(si.base_total_taxes_and_charges, 0)   AS vat_amount,
            COALESCE(si.base_grand_total, 0)               AS total_with_vat,
            COALESCE(si.status, 'Draft')                   AS status,
            si.due_date
        FROM `tabSales Invoice` si
        WHERE {" AND ".join(conds)}
        ORDER BY si.posting_date DESC, si.name DESC
        LIMIT {limit}
        """,
        vals,
        as_dict=True,
    )

    return [
        {
            "id": r.name,
            "doctype": "Sales Invoice",
            "name": r.name,
            "customer_name": r.customer_name,
            "customer": r.customer,
            "total_quantity": flt(r.total_quantity),
            "total_amount": flt(r.total_amount),
            "vat_amount": flt(r.vat_amount),
            "total_with_vat": flt(r.total_with_vat),
            "status": r.status or "Draft",
            "posting_date": str(r.posting_date) if r.posting_date else None,
            "due_date": str(r.due_date) if r.due_date else None,
            "territory": r.territory,
            "company": r.company,
        }
        for r in rows
    ]


def _resolve_company_from_access_profile(user: str) -> Optional[str]:
    """Best-effort fallback to pick the first enabled Access Profile's company for the user."""
    if not user or user == "Guest":
        return None

    try:
        meta_ap = get_meta("Access Profile")
    except Exception:
        meta_ap = None

    candidate_fields: List[str] = []
    try:
        cols = frappe.db.sql("SHOW COLUMNS FROM `tabAccess Profile`", as_dict=True)
        existing_cols = {c["Field"] for c in cols}
    except Exception:
        existing_cols = set()

    for fieldname in ("user", "user_id", "owner"):
        if fieldname in existing_cols:
            candidate_fields.append(fieldname)

    if meta_ap:
        for df in meta_ap.fields:
            if getattr(df, "options", None) == "User":
                if df.fieldname in existing_cols and df.fieldname not in candidate_fields:
                    candidate_fields.append(df.fieldname)

    if not candidate_fields:
        return None

    for fieldname in candidate_fields:
        filters = {
            fieldname: user,
            "enabled": 1,
            "docstatus": ["<", 2],
        }
        profile = frappe.db.get_value(
            "Access Profile",
            filters,
            ["company"],
            as_dict=True,
        )
        if profile and profile.company:
            return profile.company
    return None


def _fetch_delivery_notes(from_date, to_date, company, territories, limit, workflow_states=None):
    conds, vals = ["dn.docstatus = 0"], {}
    conds.append("(dn.status IS NULL OR dn.status = 'Draft')")

    if from_date and to_date:
        conds.append("dn.posting_date BETWEEN %(from)s AND %(to)s")
        vals.update({"from": from_date, "to": to_date})
    elif from_date:
        conds.append("dn.posting_date >= %(from)s")
        vals["from"] = from_date
    elif to_date:
        conds.append("dn.posting_date <= %(to)s")
        vals["to"] = to_date

    if company:
        conds.append("dn.company = %(company)s")
        vals["company"] = company
    if territories:
        cleaned = _expand_territories(territories)
        if cleaned:
            if len(cleaned) == 1:
                conds.append("dn.territory = %(territory)s")
                vals["territory"] = cleaned[0]
            else:
                conds.append("dn.territory IN %(territories)s")
                vals["territories"] = tuple(cleaned)

    if workflow_states:
        cleaned_states = [s for s in workflow_states if s]
        if cleaned_states:
            conds.append("dn.workflow_state IN %(workflow_states)s")
            vals["workflow_states"] = tuple(cleaned_states)

    rows = frappe.db.sql(
        f"""
        SELECT
            dn.name,
            dn.customer_name,
            dn.customer,
            dn.posting_date,
            dn.company,
            dn.territory,
            COALESCE(dn.total_qty, 0)                      AS total_quantity,
            COALESCE(dn.base_net_total, 0)                 AS total_amount,
            COALESCE(dn.base_total_taxes_and_charges, 0)   AS vat_amount,
            COALESCE(dn.base_grand_total, 0)               AS total_with_vat,
            COALESCE(dn.status, 'Draft')                   AS status,
            dn.workflow_state
        FROM `tabDelivery Note` dn
        WHERE {" AND ".join(conds)}
        ORDER BY dn.posting_date DESC, dn.name DESC
        LIMIT {limit}
        """,
        vals,
        as_dict=True,
    )

    return [
        {
            "id": r.name,
            "doctype": "Delivery Note",
            "name": r.name,
            "customer_name": r.customer_name,
            "customer": r.customer,
            "total_quantity": flt(r.total_quantity),
            "total_amount": flt(r.total_amount),
            "vat_amount": flt(r.vat_amount),
            "total_with_vat": flt(r.total_with_vat),
            "status": r.status or "Draft",
            "posting_date": str(r.posting_date) if r.posting_date else None,
            "due_date": None,
            "territory": r.territory,
            "company": r.company,
            "workflow_state": r.workflow_state,
        }
        for r in rows
    ]


# ----------------------- Aging -----------------------
def _compute_customer_aging(customer: str, company: str) -> Dict[str, float]:
    if not customer or not company:
        return {
            "total_outstanding": 0.0,
            "overdue_total": 0.0,
            "b0_30": 0.0,
            "b31_60": 0.0,
            "b61_90": 0.0,
            "b_over_90": 0.0,
        }

    rows = frappe.db.sql(
        """
        SELECT si.due_date, si.outstanding_amount
        FROM `tabSales Invoice` si
        WHERE
            si.customer = %(customer)s
            AND si.company = %(company)s
            AND si.docstatus = 1
            AND si.outstanding_amount > 0
        """,
        {"customer": customer, "company": company},
        as_dict=True,
    )

    b0_30 = b31_60 = b61_90 = b_over_90 = 0.0
    overdue_total = 0.0
    total_outstanding = 0.0
    today = getdate(nowdate())

    for r in rows:
        amt = flt(r.outstanding_amount)
        total_outstanding += amt
        if r.due_date:
            days = (today - getdate(r.due_date)).days
            if days > 0:
                overdue_total += amt
                if days <= 30:
                    b0_30 += amt
                elif days <= 60:
                    b31_60 += amt
                elif days <= 90:
                    b61_90 += amt
                else:
                    b_over_90 += amt

    return {
        "total_outstanding": total_outstanding,
        "overdue_total": overdue_total,
        "b0_30": b0_30,
        "b31_60": b31_60,
        "b61_90": b61_90,
        "b_over_90": b_over_90,
    }


def debug_fetch_error_logs(title: str, limit: int = 20):
    """Debug helper: return recent Error Log rows matching `title`.

    This exists to be invokable via `bench --site <site> execute "module.path.func" "title"`.
    Do NOT ship a production client that calls this.
    """
    try:
        # Use a direct SQL call to avoid reliance on doctype field names that may differ
        rows = frappe.db.sql(
            """
            SELECT *
            FROM `tabError Log`
            WHERE title = %s
            ORDER BY creation DESC
            LIMIT %s
            """,
            (title, limit),
            as_dict=True,
        )
        return rows
    except Exception:
        return {"error": frappe.get_traceback()}


@frappe.whitelist(methods=["POST"])
def reject_document(**kwargs):
	"""Reject a pending document via workflow."""
	payload = frappe._dict(kwargs or frappe.form_dict or {})
	payload.setdefault("action", "Reject")
	payload.setdefault("workflow_action", "Reject")
	return approve_document(**payload)


@frappe.whitelist(methods=["GET", "POST"], allow_guest=False)
def inbox(**kwargs):
	"""Alias for get_all_approvals (mobile inbox)."""
	return get_all_approvals(**kwargs)


@frappe.whitelist(methods=["POST"])
def apply(**kwargs):
	"""Alias for approve_document (mobile apply action)."""
	return approve_document(**kwargs)


@frappe.whitelist(methods=["GET", "POST"], allow_guest=False)
def get_complete_approvals_data(status=None, priority=None, limit=50, offset=0):
	"""Legacy aggregate approvals payload (ToDo-based)."""
	try:
		filters = {}
		if status:
			filters["status"] = status
		if priority:
			filters["priority"] = priority

		approvals = frappe.get_all(
			"ToDo",
			filters=filters,
			fields=["name", "description", "status", "priority", "owner", "creation"],
			order_by="creation desc",
			limit=limit,
			start=offset,
		)

		processed_approvals = []
		for approval in approvals:
			description = approval.description or ""
			processed_approvals.append(
				{
					"id": approval.name,
					"doctype": "ToDo",
					"name": approval.name,
					"title": description[:50] + "..." if len(description) > 50 else description,
					"status": approval.status,
					"priority": approval.priority or "Medium",
					"submitted_by": approval.owner,
					"submitted_on": approval.creation.strftime("%Y-%m-%d %H:%M:%S"),
					"description": description,
				}
			)

		return {
			"approvals": processed_approvals,
			"total_pending": frappe.db.count("ToDo", {"status": "Open"}),
			"total_approved": frappe.db.count("ToDo", {"status": "Closed"}),
			"total_rejected": frappe.db.count("ToDo", {"status": "Cancelled"}),
		}
	except Exception as e:
		frappe.log_error(f"Approvals API Error: {str(e)}")
		frappe.throw(_("Error fetching approvals data: {0}").format(str(e)))


@frappe.whitelist(methods=["GET", "POST"], allow_guest=False)
def get_approval_analytics(
	company=None,
	from_date=None,
	to_date=None,
	**kwargs,
):
	"""Mobile path: erp_analysis.approvals.get_approval_analytics"""
	from erp_analysis.approval_analytics import get_approval_summary

	return get_approval_summary(company=company, from_date=from_date, to_date=to_date)