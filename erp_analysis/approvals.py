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

from erp_analysis.utils.schema import has_column, sql_select

OBJECT_KEY_BY_DOCTYPE = {
    "Sales Invoice": "erp_analysis.approvals.sales_invoice",
    "Delivery Note": "erp_analysis.approvals.delivery_note",
}

MOBILE_APPROVAL_DOCTYPES = frozenset(OBJECT_KEY_BY_DOCTYPE.keys())

import frappe.model.workflow as _workflow_module

_ORIGINAL_APPLY_WORKFLOW = _workflow_module.apply_workflow


def _object_key_for_doctype(doctype: str) -> str:
    return OBJECT_KEY_BY_DOCTYPE.get(doctype) or f"erp_analysis.approvals.{frappe.scrub(doctype)}"


def _ensure_mobile_approve_access(
    doctype: str,
    docname: str,
    *,
    company: Optional[str] = None,
    territory: Optional[str] = None,
    branch: Optional[str] = None,
) -> Dict[str, Any]:
    """Access Profile approve territories + can_approve (not User Permission)."""
    doc_meta = frappe.db.get_value(
        doctype,
        docname,
        ["company", "territory", "branch"],
        as_dict=True,
    )
    if not doc_meta:
        frappe.throw(_("Document {0} {1} not found.").format(doctype, docname), frappe.DoesNotExistError)

    doc_company = (company or doc_meta.get("company") or "").strip()
    doc_territory = (territory or doc_meta.get("territory") or "").strip()
    doc_branch = (branch or doc_meta.get("branch") or "").strip()
    if not branch:
        branch = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "branch") or ""
    branch = (branch or "").strip()
    doc_branch = doc_branch or branch

    assert_document_territory_allowed(
        doc_meta.get("territory"), company=doc_company, purpose="approve"
    )

    object_key = _object_key_for_doctype(doctype)
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

    if not decision or not decision.get("can_approve"):
        if last_error:
            frappe.log_error(
                title="approve_document permission failure",
                message=(
                    f"doctype={doctype}, name={docname}, company={doc_company}, "
                    f"territory={doc_territory}, branch={branch}, object_key={object_key}\n{last_error}"
                ),
            )
        frappe.throw(
            f"You do not have approval access for {doctype} {docname}.",
            frappe.PermissionError,
        )
    return doc_meta


def _bypass_load_doc_before_save(self, *, raise_exception: bool = False):
    """Load _doc_before_save with ignore_permissions (workflow validate uses it)."""
    self._doc_before_save = None
    if self.is_new():
        return
    try:
        self._doc_before_save = frappe.get_doc(
            self.doctype, self.name, for_update=True, ignore_permissions=True
        )
        self._doc_before_save.flags.ignore_permissions = True
    except frappe.DoesNotExistError:
        if raise_exception:
            raise
        frappe.clear_last_message()


def _persist_doc_after_workflow(doc, *, save: bool = False, submit: bool = False, cancel: bool = False):
    """Save/submit/cancel with User Permission bypass after profile approve gate."""
    import types
    from frappe.model.document import Document

    doc.flags.ignore_permissions = True
    doc.load_doc_before_save = types.MethodType(_bypass_load_doc_before_save, doc)
    prev_flag = getattr(frappe.flags, "ignore_permissions", False)
    frappe.flags.ignore_permissions = True

    orig_get_transitions = _workflow_module.get_transitions

    def _get_transitions_bypass(d, workflow=None, raise_exception=False):
        if isinstance(d, Document):
            d.flags.ignore_permissions = True
        elif isinstance(d, dict):
            d = frappe.get_doc(d)
            d.flags.ignore_permissions = True
        return orig_get_transitions(d, workflow, raise_exception=raise_exception)

    _workflow_module.get_transitions = _get_transitions_bypass
    try:
        if submit:
            doc.submit()
        elif cancel:
            doc.cancel()
        elif save:
            doc.save(ignore_permissions=True)
    finally:
        _workflow_module.get_transitions = orig_get_transitions
        frappe.flags.ignore_permissions = prev_flag


def user_can_mobile_approve(doctype: str, docname: str, *, user: Optional[str] = None) -> bool:
    """True when Access Profile allows approve on this document (ignores User Permission)."""
    if doctype not in MOBILE_APPROVAL_DOCTYPES or not docname:
        return False
    user = user or frappe.session.user
    if user in ("Administrator", "Guest") or "System Manager" in frappe.get_roles(user):
        return user != "Guest"
    if user != frappe.session.user:
        return False
    try:
        _ensure_mobile_approve_access(doctype, docname)
        return True
    except Exception:
        return False


def _apply_workflow_trusted(doc, action: str) -> "frappe.model.document.Document":
    """Apply workflow without reloading doc (preserves ignore_permissions)."""
    from frappe.model.docstatus import DocStatus

    workflow = _workflow_module.get_workflow(doc.doctype)
    if not workflow:
        frappe.throw(_("No active workflow for {0}").format(doc.doctype))

    doc.flags.ignore_permissions = True
    transitions = _workflow_module.get_transitions(doc, workflow, raise_exception=False)
    desired = (action or "").strip()
    transition = None
    for row in transitions:
        if (row.get("action") or "") == desired:
            transition = row
            break

    if not transition:
        frappe.throw(_("Not a valid Workflow Action"), _workflow_module.WorkflowTransitionError)

    user = frappe.session.user
    if not _workflow_module.has_approval_access(user, doc, transition):
        frappe.throw(_("Self approval is not allowed"))

    doc.set(workflow.workflow_state_field, transition.get("next_state"))
    next_state = next(d for d in workflow.states if d.state == transition.get("next_state"))

    if next_state.update_field:
        doc.set(next_state.update_field, next_state.update_value)

    new_docstatus = DocStatus(next_state.doc_status or 0)
    if doc.docstatus.is_draft() and new_docstatus.is_draft():
        _persist_doc_after_workflow(doc, save=True)
    elif doc.docstatus.is_draft() and new_docstatus.is_submitted():
        _persist_doc_after_workflow(doc, submit=True)
    elif doc.docstatus.is_submitted() and new_docstatus.is_submitted():
        _persist_doc_after_workflow(doc, save=True)
    elif doc.docstatus.is_submitted() and new_docstatus.is_cancelled():
        _persist_doc_after_workflow(doc, cancel=True)
    else:
        frappe.throw(_("Illegal Document Status for {0}").format(next_state.state))

    doc.add_comment("Workflow", _(next_state.state))
    return doc


@frappe.whitelist()
def apply_workflow_mobile(doc, action):
    """
    Mobile workflow apply: bypass User Permission when user has Access Profile
    approve rights but no Desk read on the document.
    """
    if isinstance(doc, str):
        doc = frappe.parse_json(doc)
    if isinstance(doc, dict):
        doctype = doc.get("doctype")
        name = doc.get("name")
    else:
        doctype = getattr(doc, "doctype", None)
        name = getattr(doc, "name", None)

    if not doctype or not name:
        return _ORIGINAL_APPLY_WORKFLOW(doc, action)

    if doctype not in MOBILE_APPROVAL_DOCTYPES:
        return _ORIGINAL_APPLY_WORKFLOW(doc, action)

    if not user_can_mobile_approve(doctype, name):
        return _ORIGINAL_APPLY_WORKFLOW(doc, action)

    _ensure_mobile_approve_access(doctype, name)
    docobj = frappe.get_doc(doctype, name, ignore_permissions=True)
    docobj.flags.ignore_permissions = True
    prev_defer_zatca = getattr(frappe.flags, "defer_zatca_for_mobile_approve", False)
    if doctype == "Sales Invoice":
        frappe.flags.defer_zatca_for_mobile_approve = True
    try:
        return _apply_workflow_trusted(docobj, action)
    finally:
        if doctype == "Sales Invoice":
            frappe.flags.defer_zatca_for_mobile_approve = prev_defer_zatca


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

    _ensure_mobile_approve_access(
        doctype,
        docname,
        company=company or None,
        territory=territory or None,
        branch=branch or None,
    )

    doc = frappe.get_doc(doctype, docname, ignore_permissions=True)
    doc.flags.ignore_permissions = True

    workflow_applied = False
    zatca_deferred = False
    prev_defer_zatca = getattr(frappe.flags, "defer_zatca_for_mobile_approve", False)
    if doctype == "Sales Invoice":
        frappe.flags.defer_zatca_for_mobile_approve = True

    try:
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
                    _apply_workflow_trusted(doc, desired_action)
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
                _persist_doc_after_workflow(doc, submit=True)
            else:
                _persist_doc_after_workflow(doc, save=True)

        if comments:
            doc.add_comment("Comment", comments)

        if doctype == "Sales Invoice":
            zatca_deferred = True

        frappe.db.commit()
    finally:
        if doctype == "Sales Invoice":
            frappe.flags.defer_zatca_for_mobile_approve = prev_defer_zatca

    doc = frappe.get_doc(doctype, docname, ignore_permissions=True)

    zatca_status = None
    if doc.doctype == "Sales Invoice" and doc.meta.has_field("custom_zatca_status"):
        zatca_status = doc.get("custom_zatca_status")

    return {
        "message": {
            "status": "success",
            "doctype": doc.doctype,
            "name": doc.name,
            "docstatus": doc.docstatus,
            "workflow_state": getattr(doc, "workflow_state", None),
            "workflow_applied": workflow_applied,
            "workflow_action": desired_action if workflow_applied else None,
            "zatca_deferred": zatca_deferred,
            "zatca_status": zatca_status,
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

    territory = (territory or "").strip()
    if not territory:
        default_territory = (frappe.defaults.get_user_default("Territory") or "").strip()
        if default_territory and default_territory.lower() not in ("all territories", "all"):
            territory = default_territory
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
        try:
            approvals.extend(
                _fetch_sales_invoices(
                    from_date, to_date, company_filter, territory_filters, limit
                )
            )
        except Exception:
            frappe.log_error(
                title="approvals._fetch_sales_invoices",
                message=frappe.get_traceback(),
            )

    if "Delivery Note" in wanted_doctypes and _check("erp_analysis.approvals.delivery_note"):
        try:
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
        except Exception:
            frappe.log_error(
                title="approvals._fetch_delivery_notes",
                message=frappe.get_traceback(),
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
    doctype = "Sales Invoice"
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

    if territories and has_column(doctype, "territory"):
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
            {sql_select(doctype, "si", "customer_name")},
            {sql_select(doctype, "si", "customer")},
            si.posting_date,
            {sql_select(doctype, "si", "company")},
            {sql_select(doctype, "si", "territory")},
            {sql_select(doctype, "si", "total_qty", as_name="total_quantity", coalesce="0")},
            {sql_select(doctype, "si", "base_net_total", as_name="total_amount", coalesce="0")},
            {sql_select(doctype, "si", "base_total_taxes_and_charges", as_name="vat_amount", coalesce="0")},
            {sql_select(doctype, "si", "base_grand_total", as_name="total_with_vat", coalesce="0")},
            COALESCE(si.status, 'Draft') AS status,
            {sql_select(doctype, "si", "due_date")},
            {sql_select(doctype, "si", "workflow_state")}
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
            "workflow_state": r.workflow_state,
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
    doctype = "Delivery Note"
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

    if territories and has_column(doctype, "territory"):
        cleaned = _expand_territories(territories)
        if cleaned:
            if len(cleaned) == 1:
                conds.append("dn.territory = %(territory)s")
                vals["territory"] = cleaned[0]
            else:
                conds.append("dn.territory IN %(territories)s")
                vals["territories"] = tuple(cleaned)

    # Workflow filter is Printechs-specific; skip when column/meta missing (e.g. Ozdah).
    if workflow_states and has_column(doctype, "workflow_state"):
        cleaned_states = [s for s in workflow_states if s]
        if cleaned_states:
            conds.append("dn.workflow_state IN %(workflow_states)s")
            vals["workflow_states"] = tuple(cleaned_states)

    rows = frappe.db.sql(
        f"""
        SELECT
            dn.name,
            {sql_select(doctype, "dn", "customer_name")},
            {sql_select(doctype, "dn", "customer")},
            dn.posting_date,
            {sql_select(doctype, "dn", "company")},
            {sql_select(doctype, "dn", "territory")},
            {sql_select(doctype, "dn", "total_qty", as_name="total_quantity", coalesce="0")},
            {sql_select(doctype, "dn", "base_net_total", as_name="total_amount", coalesce="0")},
            {sql_select(doctype, "dn", "base_total_taxes_and_charges", as_name="vat_amount", coalesce="0")},
            {sql_select(doctype, "dn", "base_grand_total", as_name="total_with_vat", coalesce="0")},
            COALESCE(dn.status, 'Draft') AS status,
            {sql_select(doctype, "dn", "workflow_state")}
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