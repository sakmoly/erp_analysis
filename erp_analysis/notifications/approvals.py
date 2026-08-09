from __future__ import annotations

import json
from typing import Dict, Iterable, Optional

import requests

import frappe

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
APPROVAL_STATES = {"Pending Approval", "Awaiting Approval"}


def notify_pending_approval(doc, method: Optional[str] = None):
    """Fired via hooks when Sales Invoice / Delivery Note enters Pending Approval."""
    try:
        workflow_state = getattr(doc, "workflow_state", None)
        if not workflow_state or workflow_state not in APPROVAL_STATES:
            return

        territory = getattr(doc, "territory", None)
        company = getattr(doc, "company", None)
        tokens = list(_get_tokens(company=company, territory=territory))
        if not tokens:
            return

        title = f"{doc.doctype} awaiting approval"
        body = f"{doc.name} ({territory or 'No Territory'})"
        data = {"doctype": doc.doctype, "name": doc.name, "territory": territory}

        for token_row in tokens:
            payload = {
                "to": token_row["expo_token"],
                "sound": "default",
                "title": title,
                "body": body,
                "data": data,
            }
            _send_expo_push(payload, token_row["name"])
    except Exception:
        frappe.log_error(frappe.get_traceback(), "notify_pending_approval failed")


def _get_tokens(company: Optional[str], territory: Optional[str]) -> Iterable[Dict[str, str]]:
    """Return Mobile Push Tokens matching company/territory scope."""
    conditions = ["docstatus = 0"]
    params = {}

    if company:
        conditions.append("(company IS NULL OR company = '' OR company = %(company)s)")
        params["company"] = company
    if territory:
        conditions.append("(territory IS NULL OR territory = '' OR territory = %(territory)s)")
        params["territory"] = territory

    where = " AND ".join(conditions)
    query = f"""SELECT name, expo_token FROM `tabMobile Push Token` WHERE {where}"""
    return frappe.db.sql(query, params, as_dict=True)


def _send_expo_push(payload: Dict[str, str], token_name: str):
    """Post payload to Expo Push API, removing invalid tokens when necessary."""
    try:
        response = requests.post(EXPO_PUSH_URL, json=payload, timeout=5)
        response.raise_for_status()
        data = response.json()
        if data.get("data", {}).get("status") == "error":
            _handle_expo_error(data, token_name)
    except Exception:
        frappe.log_error(
            title="Expo Push Failure",
            message=f"token={token_name}\npayload={json.dumps(payload, indent=2)}\n{frappe.get_traceback()}",
        )


def _handle_expo_error(response_data: Dict[str, Dict[str, str]], token_name: str):
    error = response_data.get("data", {}).get("details", {}).get("error")
    if error in {"DeviceNotRegistered", "MessageTooBig", "InvalidCredentials"}:
        frappe.db.delete("Mobile Push Token", {"name": token_name})

