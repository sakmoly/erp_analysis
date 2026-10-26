# apps/erp_analysis/erp_analysis/customer_notifications.py

from __future__ import annotations

import base64
import json
import typing as t
from contextlib import contextmanager

import frappe
from frappe import _
from frappe.utils.file_manager import save_file
from frappe.utils.pdf import get_pdf
from datetime import datetime, timedelta
from frappe.utils import nowdate, date_diff, flt, getdate, add_days

from erp_analysis.permissions.access_profile import assert_document_territory_allowed, bypass_view_territories
from erp_analysis.services.statement_branding import (
	SOA_PRINT_FORMAT,
	build_statement_branding,
	wrap_mobile_message,
)
from erp_analysis.utils.rpc import (
	absolute_file_url,
	clean_kwargs,
	expand_rpc_kwargs,
	get_arg,
	get_date_arg,
)

SOA_PDF_OBJECT_KEYS = (
	"erp_analysis.customer_notifications.get_statement_pdf",
	"printechs_utility.customer_notifications.get_statement_pdf",
)

# =========================
# PUBLIC API ENDPOINTS
# =========================

def get_email_list(customer_name: str) -> list[str]:
    """Return unique email IDs for a Customer's linked Contacts safely."""
    # Find Contacts linked to this Customer via Dynamic Link
    links = frappe.get_all(
        "Dynamic Link",
        filters={"link_doctype": "Customer", "link_name": customer_name, "parenttype": "Contact"},
        fields=["parent"]
    )
    if not links:
        return []

    contact_names = [l.parent for l in links]
    if not contact_names:
        return []

    # Fetch emails from Contact Email child table
    rows = frappe.get_all(
        "Contact Email",
        filters={"parent": ["in", contact_names], "email_id": ["!=", ""]},
        fields=["email_id"]
    )

    # Deduplicate, keep order
    seen, emails = set(), []
    for r in rows:
        e = (r.get("email_id") or "").strip()
        if e and e.lower() not in seen:
            seen.add(e.lower())
            emails.append(e)
    return emails


def _resolve_statement_customer(customer_name=None, customer=None) -> str:
    name = (customer_name or customer or get_arg("customer_name") or get_arg("customer") or "").strip()
    if not name:
        frappe.throw(_("Customer is required"))
    if not frappe.db.exists("Customer", name):
        frappe.throw(_("Customer {0} not found").format(name))
    return name


def _assert_statement_territory_access(customer_name: str, company: str | None) -> str:
    company = company or frappe.defaults.get_user_default("Company")
    cust_territory = frappe.db.get_value("Customer", customer_name, "territory")
    if not bypass_view_territories("receivables", company=company):
        assert_document_territory_allowed(cust_territory, company=company, purpose="view")
    return company


def _enforce_soa_pdf_api_access(company: str | None) -> bool:
	"""
	Access Profile users must have ``get_statement_pdf`` on their profile and pass territory checks
	(see ``_assert_statement_territory_access``). They may lack ERPNext Customer print role.

	Users **without** an Access Profile keep standard desk rules: Customer ``print`` permission required.

	Returns True when profile governs the call (controlled print bypass). Raises PermissionError when
	a profile exists but the API object is not permitted.
	"""
	from erp_analysis.permissions.access_profile import PermissionDenied, _get_user_profile_name, evaluate

	user = frappe.session.user
	company = company or frappe.defaults.get_user_default("Company")
	if not _get_user_profile_name(user, company):
		return False

	for object_key in SOA_PDF_OBJECT_KEYS:
		try:
			if evaluate(user, company, None, None, object_key).get("can_view"):
				return True
		except PermissionDenied:
			continue

	frappe.throw(
		_("Access denied for {0}").format(SOA_PDF_OBJECT_KEYS[0]),
		frappe.PermissionError,
	)


def _default_statement_dates(from_date=None, to_date=None) -> tuple[str, str]:
    to_date = get_date_arg("to_date", default=to_date) or str(nowdate())
    from_date = get_date_arg("from_date", default=from_date)
    if not from_date:
        from_date = str(getdate(add_days(to_date, -90)))
    return str(from_date), str(to_date)


@frappe.whitelist(allow_guest=False, methods=["GET", "POST"])
def get_statement_branding(
    customer_name: str | None = None,
    company: str | None = None,
    customer: str | None = None,
    **kwargs,
):
    """Letterhead + bank footer for mobile on-device SOA PDF (matches desk SOA print format)."""
    expand_rpc_kwargs(kwargs)
    customer_name = _resolve_statement_customer(customer_name, customer or get_arg("customer"))
    company = get_arg("company", default=company) or frappe.defaults.get_user_default("Company")
    company = _assert_statement_territory_access(customer_name, company)
    return wrap_mobile_message(build_statement_branding(company, customer_name))


def _resolve_soa_print_format(default: str | None = None) -> str:
	pf = get_arg("print_format", default=default) or default or SOA_PRINT_FORMAT
	if not frappe.db.exists("Print Format", pf):
		frappe.throw(_("Print Format {0} not found").format(pf))
	return pf


def _build_statement_pdf_payload(
	customer_name: str,
	company: str,
	from_date: str,
	to_date: str,
	print_format: str | None = None,
	return_pdf: bool = False,
	return_file_url: bool = True,
	profile_governed: bool = False,
) -> dict:
	"""Desk-equivalent SOA PDF for mobile share (no email). Dates are metadata only."""
	print_format = print_format or _resolve_soa_print_format()
	pdf, fname, soa_meta = _generate_customer_soa_pdf(
		customer_name,
		company=company,
		print_format=print_format,
		profile_governed=profile_governed,
		privileged_soa_render=True,
	)
	branding = build_statement_branding(company, customer_name)
	payload: dict = {
		"filename": fname,
		"customer_name": customer_name,
		"company": company,
		"from_date": from_date,
		"to_date": to_date,
		"print_format": print_format,
		"statement_pdf_scope": "outstanding_invoices",
		"requested_period": {"from_date": from_date, "to_date": to_date},
		"soa_body_present": soa_meta.get("soa_body_present"),
		"soa_pdf_verified": bool(soa_meta.get("soa_body_present")),
		"outstanding_invoice_count": soa_meta.get("outstanding_invoice_count"),
		"branding": branding,
		**branding,
	}
	if return_file_url:
		file_doc = save_file(fname, pdf, "Customer", customer_name, is_private=1)
		payload["file_url"] = file_doc.file_url
		payload["pdf_url"] = absolute_file_url(file_doc.file_url)
	if return_pdf:
		payload["pdf_base64"] = base64.b64encode(pdf).decode("ascii")
	if not return_file_url and not return_pdf:
		file_doc = save_file(fname, pdf, "Customer", customer_name, is_private=1)
		payload["file_url"] = file_doc.file_url
		payload["pdf_url"] = absolute_file_url(file_doc.file_url)
	return payload


@frappe.whitelist(allow_guest=False, methods=["GET", "POST"])
def get_statement_pdf(
    customer_name: str | None = None,
    company: str | None = None,
    customer: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    print_format: str | None = None,
    return_pdf: int | str | None = None,
    return_file_url: int | str | None = None,
    send_email: int | str | None = None,
    **kwargs,
):
    """
    Generate customer SOA PDF for mobile share (WhatsApp, Mail, etc.).
    Uses desk print format ``Customer Outstanding SOA`` (current outstanding invoices).
    Does not send email. ``from_date`` / ``to_date`` are metadata only.
    """
    expand_rpc_kwargs(kwargs)
    customer_name = _resolve_statement_customer(
        customer_name, customer or get_arg("customer")
    )
    company = get_arg("company", default=company) or frappe.defaults.get_user_default("Company")
    profile_governed = _enforce_soa_pdf_api_access(company)
    company = _assert_statement_territory_access(customer_name, company)
    from_date, to_date = _default_statement_dates(from_date, to_date)
    print_format = _resolve_soa_print_format(print_format or SOA_PRINT_FORMAT)
    want_pdf = frappe.utils.cint(get_arg("return_pdf", default=return_pdf))
    want_file = get_arg("return_file_url", default=return_file_url)
    if want_file is None or want_file == "":
        want_file_url = True
    else:
        want_file_url = bool(frappe.utils.cint(want_file))

    payload = _build_statement_pdf_payload(
        customer_name,
        company,
        from_date,
        to_date,
        print_format=print_format,
        return_pdf=bool(want_pdf),
        return_file_url=want_file_url,
        profile_governed=profile_governed,
    )
    return wrap_mobile_message(payload)


@frappe.whitelist(allow_guest=False, methods=["GET", "POST"])
def send_statement_pdf(
    customer_name: str | None = None,
    send_email=1,
    return_pdf=0,
    company: str | None = None,
    customer: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    print_format: str | None = None,
    **kwargs,
):
    expand_rpc_kwargs(kwargs)
    customer_name = _resolve_statement_customer(
        customer_name, customer or get_arg("customer")
    )
    send_email = frappe.utils.cint(get_arg("send_email", default=send_email))
    return_pdf = frappe.utils.cint(get_arg("return_pdf", default=return_pdf))
    if not send_email or return_pdf:
        return get_statement_pdf(
            customer_name=customer_name,
            company=get_arg("company", default=company),
            customer=customer,
            from_date=get_arg("from_date", default=from_date),
            to_date=get_arg("to_date", default=to_date),
            print_format=get_arg("print_format", default=print_format),
            return_pdf=return_pdf,
            send_email=0,
        )
    # --- 1) Customer & recipients -------------------------------------------
    customer = frappe.get_doc("Customer", customer_name)

    # Build base recipients from your own helper (keep your existing function)
    recipients = get_email_list(customer_name)
    if not recipients:
        frappe.throw(_("Customer does not have a valid email address."))

    # Territory → add CC (internal)
    territory_email_map = {
        "Dammam": ["accntsdmm@printechs.com","salesdmmam@printechs.com","supportdammam@printechs.com"],
        "Riyadh": ["accntsryd@printechs.com", "ashraf@printechs.com"],
        "Jeddah": ["israr@printechs.com", "thanveer@printechs.com","nihal@printechs.com"],
    }
    cc_list = territory_email_map.get(customer.get("territory") or "", [])

    # Sender identity
    user_email = frappe.auth.get_logged_user()
    full_name, mobile = frappe.get_value("User", user_email, ["full_name", "mobile_no"])

    # --- 2) Generate the SOA PDF (your existing print format) ----------------
    pdf, pdf_fname, _soa_meta = _generate_customer_soa_pdf(
        customer_name, print_format=SOA_PRINT_FORMAT
    )

    # Optionally: a public print URL with signature (no login)
    site_url = frappe.utils.get_url()
    soa_url = "{}/printview?doctype=Customer&name={}&format=Customer Outstanding SOA&key={}&no_letterhead=0".format(
        site_url, customer_name, customer.get_signature()
    )

    # --- 3) Compute aging buckets -------------------------------------------
    invoices = frappe.get_all(
        "Sales Invoice",
        filters={"docstatus": 1, "customer": customer_name, "outstanding_amount": (">", 10)},
        fields=["name", "due_date", "posting_date", "outstanding_amount"]
    )

    today = nowdate()
    buckets = dict(current=0.0, d1_30=0.0, d31_60=0.0, d61_90=0.0, d91_120=0.0, d120p=0.0)
    total_all = 0.0
    overdue_sum = 0.0

    for r in invoices:
        amt = flt(r.outstanding_amount or 0)
        total_all += amt
        diff = date_diff(today, r.due_date) if r.due_date else 0

        if diff > 0:
            overdue_sum += amt

        if diff <= 0:
            buckets["current"] += amt
        elif diff <= 30:
            buckets["d1_30"] += amt
        elif diff <= 60:
            buckets["d31_60"] += amt
        elif diff <= 90:
            buckets["d61_90"] += amt
        elif diff <= 120:
            buckets["d91_120"] += amt
        else:
            buckets["d120p"] += amt

    # --- 4) Render the email body (inline Jinja template, no f-string) -------
    body_template = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
</head>
<body style="margin:0;padding:0;font-family:Arial,Helvetica,sans-serif;background-color:#ffffff;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#ffffff;width:100%;">
    <!-- Header -->
    <tr>
      <td style="background-color:#2563eb;padding:40px 60px;text-align:center;width:100%;">
        <h1 style="margin:0;color:#ffffff;font-size:28px;font-weight:bold;">Statement of Account</h1>
      </td>
    </tr>

    <!-- Content -->
    <tr>
      <td style="padding:50px 60px;width:100%;color:#333333;font-size:16px;line-height:26px;">
        <p style="margin:0 0 18px 0;font-size:18px;">Dear Valued Customer,</p>
        <p style="margin:0 0 18px 0;font-size:18px;">
            We sincerely appreciate your continued business and the trust you have placed in Printechs (Advanced Printing Trading Co.).
            However, we wish to draw your attention to the outstanding payment of <strong style="color:#b91c1c;"> SAR {{ frappe.utils.fmt_money(overdue_sum, 2) }}
            </strong>, 
            which remains unsettled despite our previous reminder. We kindly request that you arrange the payment at your earliest convenience to avoid any interruption in our services.

            For your reference, we are also attaching the summary of outstanding and overdue invoices as detailed below:
        </p>

        <div align="center" style="margin:18px 0 8px 0;">
          <table border="1" cellpadding="8" cellspacing="0" width="100%" style="border-collapse:collapse;">
            <tbody>
              <tr style="background:#f3f4f6;">
                <td width="60%"><div style="text-align:left;"><strong>Summary Bucket</strong></div></td>
                <td width="40%"><div style="text-align:right;"><strong>Amount (SAR)</strong></div></td>
              </tr>

              <tr>
                <td><div style="text-align:left;">Current (Not Due)</div></td>
                <td><div style="text-align:right;">{{ frappe.utils.fmt_money(buckets.current, 2) }}</div></td>
              </tr>
              <tr>
                <td><div style="text-align:left;"> 1–30 Days</div></td>
                <td><div style="text-align:right;">{{ frappe.utils.fmt_money(buckets.d1_30, 2) }}</div></td>
              </tr>
              <tr>
                <td><div style="text-align:left;">Overdue 31–60 Days</div></td>
                <td><div style="text-align:right;">{{ frappe.utils.fmt_money(buckets.d31_60, 2) }}</div></td>
              </tr>
              <tr>
                <td><div style="text-align:left;">Overdue 61–90 Days</div></td>
                <td><div style="text-align:right;">{{ frappe.utils.fmt_money(buckets.d61_90, 2) }}</div></td>
              </tr>
              <tr>
                <td><div style="text-align:left;">Overdue 91–120 Days</div></td>
                <td><div style="text-align:right;">{{ frappe.utils.fmt_money(buckets.d91_120, 2) }}</div></td>
              </tr>
              <tr>
                <td><div style="text-align:left;">Overdue &gt;120 Days</div></td>
                <td><div style="text-align:right;">{{ frappe.utils.fmt_money(buckets.d120p, 2) }}</div></td>
              </tr>

              <tr style="background:#f9fafb;">
                <td><div style="text-align:left;"><strong>Total Outstanding</strong></div></td>
                <td><div style="text-align:right;"><strong>{{ frappe.utils.fmt_money(total_all, 2) }}</strong></div></td>
              </tr>
            </tbody>
          </table>
        </div>

        <p style="margin:18px 0 12px 0;">
          If the amount remains unpaid, we are compelled to unfortunately, discontinue the credit facility temporary,
          until the full payment is received.
        </p>
        <p style="margin:0 0 18px 0;">
          Prompt response and quick compliance from you will help us to serve you better.
          Should you have any queries, feel free to contact our accounts departments.
        </p>
        <p style="margin:0 0 18px 0;">Your close assistance in this matter is highly appreciated.</p>
        <p style="margin:0 0 18px 0;">Yours truly,</p>
        <p style="margin:0 0 10px 0;">
          Email: {{ frappe.db.get_value("User", {"name":frappe.session.user}, "email") }}
        </p>

        <!-- Optional: show a public link for convenience -->

        <!-- Footer -->
        <table width="100%" cellpadding="0" cellspacing="0" style="border-top:2px solid #e5e5e5;padding-top:30px;margin-top:30px;">
          <tr>
            <td style="color:#666666;font-size:16px;line-height:24px;">
              <p style="margin:0 0 12px 0;"><strong style="color:#333333;">Sent by:</strong> {{ full_name or user_email }}{% if mobile %} • {{ mobile }}{% endif %}</p>
              <p style="margin:0;color:#999999;font-size:14px;">If you have any questions, please don't hesitate to contact us.</p>
            </td>
          </tr>
        </table>

      </td>
    </tr>
  </table>
</body>
</html>
    """

    ctx = {
        "customer_name": customer_name,
        "buckets": buckets,
        "total_all": total_all,
        "overdue_sum": overdue_sum,
        "full_name": full_name,
        "user_email": user_email,
        "mobile": mobile,
        "soa_url": soa_url,  # optional use in template
    }

    body = frappe.render_template(body_template, ctx)

    # --- 5) Send email -------------------------------------------------------
    frappe.sendmail(
        recipients=recipients,
        cc=cc_list,
        subject=f"Your Statement of Account - {customer_name}",
        message=body,
        attachments=[{"fname": pdf_fname, "fcontent": pdf}],
        reference_doctype="Customer",
        reference_name=customer_name,
        sender="Notifications <support@printechs.com>",
        reply_to=user_email,
        expose_recipients="header",
    )

    # --- 6) Log Communication ------------------------------------------------
    all_visible = recipients + (cc_list or [])
    comm = frappe.get_doc({
        "doctype": "Communication",
        "subject": f"Statement of Account Sent - {customer_name}",
        "content": f"SOA sent to: {', '.join(all_visible)}",
        "communication_type": "Automated Message",
        "communication_medium": "Email",
        "sent_or_received": "Sent",
        "recipients": ", ".join(all_visible),
        "reference_doctype": "Customer",
        "reference_name": customer_name,
    })
    comm.insert(ignore_permissions=True)

    return {"message": f"Statement of Account sent successfully to {all_visible}"}


@frappe.whitelist(allow_guest=False, methods=["POST"])
def OLDsend_statement_pdf(customer_name: str):
    """
    Send Statement of Account (SOA) to the customer with a PDF attachment.

    Request JSON:
      { "customer_name": "CUST-0001" }

    Returns:
      {
        "success": True,
        "message": "Statement sent to a@b.com, c@d.com",
        "recipients": [...],
        "cc": [...],
        "timestamp": "YYYY-MM-DD HH:MM:SS"
      }
    """
    try:
        # Validation
        if not customer_name:
            frappe.throw(_("Customer name is required"))

        # Customer doc
        try:
            customer = frappe.get_doc("Customer", customer_name)
        except frappe.DoesNotExistError:
            frappe.throw(_("Customer '{0}' not found").format(customer_name))

        # Rate limit (3 calls / 60 minutes)
        _check_rate_limit(customer_name, "statement_pdf", max_calls=20, window_minutes=60)

        # PDF (SOA)
        pdf, pdf_filename, _soa_meta = _generate_customer_soa_pdf(customer_name)

        # Recipients / CC
        recipients = _get_validated_recipients(customer_name)
        cc_list = _get_territory_cc_list(customer)

        # URL to form (view link)
        soa_url = _generate_soa_url(customer_name)

        # Sender
        sender_details = _get_sender_details()

        # Email body
        email_body = _generate_email_body(
            customer_name=customer_name,
            soa_url=soa_url,
            sender_details=sender_details
        )

        # Send
        frappe.sendmail(
            recipients=recipients,
            cc=cc_list,
            subject=f"Statement of Account - {customer_name}",
            message=email_body,
            attachments=[{"fname": pdf_filename, "fcontent": pdf}],
            reference_doctype="Customer",
            reference_name=customer_name,
            sender="Notifications <support@printechs.com>",
            reply_to=sender_details["email"],
            expose_recipients="header"
        )

        # Log communication
        _log_communication(
            recipients=recipients + cc_list,
            subject=f"Statement of Account - {customer_name}",
            doctype="Customer",
            name=customer_name
        )

        frappe.logger().info(f"SOA sent to {customer_name} by {sender_details['user']}")
        return {
            "success": True,
            "message": "Statement sent to {0}".format(", ".join(recipients)),
            "recipients": recipients,
            "cc": cc_list,
            "timestamp": frappe.utils.now()
        }

    except Exception as e:
        frappe.logger().error(f"Error sending SOA to {customer_name}: {frappe.get_traceback()}")
        frappe.throw(_("Failed to send statement: {0}").format(str(e)))


@frappe.whitelist(allow_guest=False, methods=["POST"])
def send_payment_overdue_notice(customer_name: str, overdue_amount: t.Optional[float] = None):
    """
    Send Payment Overdue Notice to the customer with aging analysis and PDFs.

    Request JSON:
      { "customer_name": "CUST-0001", "overdue_amount": 12345.67 }  # overdue_amount optional

    Returns:
      {
        "success": True,
        "message": "Payment overdue notice sent to a@b.com",
        "recipients": [...],
        "cc": [...],
        "overdue_amount": 12345.67,
        "timestamp": "YYYY-MM-DD HH:MM:SS"
      }
    """
    try:
        if not customer_name:
            frappe.throw(_("Customer name is required"))

        customer = frappe.get_doc("Customer", customer_name)

        # Rate limit (1 per 24h)
        _check_rate_limit(customer_name, "overdue_notice", max_calls=1, window_minutes=24 * 60)

        overdue_data = _calculate_overdue_details(customer_name, overdue_amount)

        if not overdue_data["total_overdue"] or overdue_data["total_overdue"] <= 0:
            frappe.throw(_("No overdue amount found for this customer"))

        # PDFs
        overdue_pdf, overdue_pdf_filename = _generate_overdue_statement_pdf(customer_name, overdue_data)
        aging_pdf = _generate_aging_analysis_pdf(customer_name)

        recipients = _get_validated_recipients(customer_name)
        cc_list = _get_territory_cc_list_for_overdue(customer, overdue_data)

        sender_details = _get_sender_details()
        email_body = _generate_overdue_email_body(
            customer_name=customer_name,
            overdue_data=overdue_data,
            sender_details=sender_details
        )

        # Send
        frappe.sendmail(
            recipients=recipients,
            cc=cc_list,
            subject=f"🔴 URGENT: Payment Overdue Notice - {customer_name}",
            message=email_body,
            attachments=[
                {"fname": overdue_pdf_filename, "fcontent": overdue_pdf},
                {"fname": f"Aging_Analysis_{customer_name}.pdf", "fcontent": aging_pdf},
            ],
            reference_doctype="Customer",
            reference_name=customer_name,
            sender="Finance Department <finance@printechs.com>",
            reply_to=sender_details["email"],
            expose_recipients="header",
            priority="High"
        )

        _log_communication(
            recipients=recipients + cc_list,
            subject=f"Payment Overdue Notice - {customer_name}",
            doctype="Customer",
            name=customer_name,
            notes=f"Overdue Amount: {overdue_data['total_overdue']}"
        )

        frappe.db.set_value("Customer", customer_name, "last_overdue_sent", frappe.utils.now())
        frappe.db.commit()

        return {
            "success": True,
            "message": "Payment overdue notice sent to {0}".format(", ".join(recipients)),
            "recipients": recipients,
            "cc": cc_list,
            "overdue_amount": overdue_data["total_overdue"],
            "timestamp": frappe.utils.now()
        }

    except Exception as e:
        frappe.logger().error(f"Error sending overdue notice to {customer_name}: {frappe.get_traceback()}")
        frappe.throw(_("Failed to send payment overdue notice: {0}").format(str(e)))


# =========================
# HELPERS
# =========================

def _check_rate_limit(customer_name: str, action_type: str, max_calls: int, window_minutes: int):
    """
    Prevent spam by limiting API calls per customer.
    Stores list of ISO timestamps in Redis (JSON string).
    """
    cache_key = f"{action_type}_{customer_name}"

    # ----- Read & deserialize -----
    raw = frappe.cache().get(cache_key)
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    try:
        recent_calls = json.loads(raw) if raw else []
    except Exception:
        recent_calls = []

    # ----- Compute cutoff using stdlib -----
    now_dt = datetime.now()
    cutoff_dt = now_dt - timedelta(minutes=window_minutes)

    # recent_calls are strings -> parse to datetime safely
    def _parse(ts: str):
        # supports 'YYYY-MM-DD HH:MM:SS(.ffffff)' from datetime.now().isoformat()
        try:
            # try with microseconds
            return datetime.fromisoformat(ts)
        except ValueError:
            # fallback without microseconds
            try:
                return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S.%f")
            except ValueError:
                return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")

    # Filter out old entries
    recent_calls = [ts for ts in recent_calls if _parse(ts) > cutoff_dt]

    if len(recent_calls) >= max_calls:
        frappe.throw(_("Too many requests. Please try again later."))

    # ----- Append current call & write back -----
    now_str = datetime.now().isoformat()
    recent_calls.append(now_str)

    frappe.cache().setex(cache_key, window_minutes * 60, json.dumps(recent_calls))



def _generate_overdue_statement_pdf(customer_name: str, overdue_data: dict) -> tuple[bytes, str]:
    """Generate Payment Overdue notice PDF using a template; fallback to minimal HTML."""
    try:
        html = frappe.render_template("templates/emails/overdue_statement.html", {
            "customer_name": customer_name,
            "overdue_data": overdue_data,
            "date": frappe.utils.formatdate(frappe.utils.today()),
            "money": frappe.utils.fmt_money,
        })
    except Exception:
        # Fallback HTML
        html = f"""
            <h2>Payment Overdue Notice</h2>
            <p><b>Customer:</b> {frappe.utils.escape_html(customer_name)}</p>
            <p><b>Total Overdue:</b> {frappe.utils.fmt_money(overdue_data.get('total_overdue') or 0)}</p>
            <p><b>Total Outstanding:</b> {frappe.utils.fmt_money(overdue_data.get('total_outstanding') or 0)}</p>
        """
    pdf = get_pdf(html)
    filename = f"Payment_Overdue_Notice_{customer_name}.pdf"
    return pdf, filename


def _get_validated_recipients(customer_name: str) -> list[str]:
    """Resolve recipient emails from linked Contacts; fallback to Customer.email_id."""
    rows = frappe.db.sql("""
        SELECT DISTINCT ce.email_id
        FROM `tabDynamic Link` dl
        JOIN `tabContact Email` ce ON ce.parent = dl.parent
        WHERE dl.link_doctype = 'Customer' AND dl.link_name = %s
    """, customer_name, as_dict=True)

    recipients = [r.email_id for r in rows if r.get("email_id")]

    if not recipients:
        email = frappe.get_value("Customer", customer_name, "email_id")
        if email:
            recipients = [email]

    # sanitize
    recipients = [e.strip() for e in recipients if e and isinstance(e, str) and "@" in e]
    if not recipients:
        frappe.throw(_("Customer does not have a valid email address"))
    return recipients


def _get_territory_cc_list(customer) -> list[str]:
    """CC list by Territory (DocType 'Territory Email Settings' or fallback map)."""
    territory = customer.get("territory")
    cc: list[str] = []

    if territory:
        try:
            value = frappe.get_cached_value("Territory Email Settings", territory, "notification_emails")
            if value:
                cc = [e.strip() for e in value.split(",") if e.strip()]
        except Exception:
            cc = []

    if not cc:
        fallback_map = {
            "Dammam": ["gks.thomas@gmail.com"],
            "Riyadh": ["accntsryd@printechs.com", "ashraf@printechs.com"],
            "Jeddah": ["israr@printechs.com", "thanveer@printechs.com"],
        }
        cc = fallback_map.get(territory, [])

    return cc


def _get_territory_cc_list_for_overdue(customer, overdue_data: dict) -> list[str]:
    """CC list for overdue notices (adds finance + territory sales manager on large amounts)."""
    cc = set(_get_territory_cc_list(customer))

    if (overdue_data.get("total_overdue") or 0) > 50000:
        cc.add("finance@printechs.com")

    if (overdue_data.get("total_overdue") or 0) > 100000:
        try:
            manager_user = frappe.get_value("Territory", customer.get("territory"), "sales_manager")
            if manager_user:
                manager_email = frappe.get_value("User", manager_user, "email")
                if manager_email:
                    cc.add(manager_email)
        except Exception:
            pass

    return sorted({e.strip() for e in cc if e and "@" in e})


def _calculate_overdue_details(customer_name: str, overdue_amount: t.Optional[float] = None) -> dict:
    """Compute total outstanding, overdue, and aging buckets for a Customer."""
    if overdue_amount is None:
        result = frappe.db.sql("""
            SELECT 
                COALESCE(SUM(outstanding_amount), 0) AS total_outstanding,
                COALESCE(SUM(CASE WHEN due_date < CURDATE() THEN outstanding_amount ELSE 0 END), 0) AS total_overdue
            FROM `tabSales Invoice`
            WHERE customer = %s AND docstatus = 1 AND outstanding_amount > 0
        """, customer_name, as_dict=True)[0]
        total_outstanding = result.total_outstanding or 0
        total_overdue = result.total_overdue or 0
    else:
        total_overdue = overdue_amount
        result = frappe.db.sql("""
            SELECT COALESCE(SUM(outstanding_amount), 0) AS total_outstanding
            FROM `tabSales Invoice`
            WHERE customer = %s AND docstatus = 1 AND outstanding_amount > 0
        """, customer_name, as_dict=True)[0]
        total_outstanding = result.total_outstanding or 0

    aging = frappe.db.sql("""
        SELECT 
            COALESCE(SUM(CASE WHEN DATEDIFF(CURDATE(), due_date) BETWEEN 0 AND 30  THEN outstanding_amount ELSE 0 END), 0) AS outstanding_0_30,
            COALESCE(SUM(CASE WHEN DATEDIFF(CURDATE(), due_date) BETWEEN 31 AND 60 THEN outstanding_amount ELSE 0 END), 0) AS outstanding_31_60,
            COALESCE(SUM(CASE WHEN DATEDIFF(CURDATE(), due_date) BETWEEN 61 AND 90 THEN outstanding_amount ELSE 0 END), 0) AS outstanding_61_90,
            COALESCE(SUM(CASE WHEN DATEDIFF(CURDATE(), due_date) > 90 THEN outstanding_amount ELSE 0 END), 0) AS outstanding_over_90
        FROM `tabSales Invoice`
        WHERE customer = %s AND docstatus = 1 AND outstanding_amount > 0
    """, customer_name, as_dict=True)[0]

    return {
        "total_outstanding": float(total_outstanding),
        "total_overdue": float(total_overdue),
        "outstanding_0_30": float(aging.outstanding_0_30 or 0),
        "outstanding_31_60": float(aging.outstanding_31_60 or 0),
        "outstanding_61_90": float(aging.outstanding_61_90 or 0),
        "outstanding_over_90": float(aging.outstanding_over_90 or 0),
    }


def _generate_soa_url(customer_name: str) -> str:
    """Generate a simple link to the Customer form (you can replace with a signed URL if needed)."""
    return frappe.utils.get_url_to_form("Customer", customer_name)


def _get_sender_details() -> dict:
    """Return current user’s display info."""
    user = frappe.session.user or frappe.auth.get_logged_user()
    full_name, mobile, email = frappe.get_value("User", user, ["full_name", "mobile_no", "email"])
    return {
        "user": user,
        "full_name": full_name,
        "mobile": mobile,
        "email": email or user
    }


def _generate_email_body(customer_name: str, soa_url: str, sender_details: dict) -> str:
    """Basic SOA email body."""
    safe_name = frappe.utils.escape_html(customer_name)
    sender_line = frappe.utils.escape_html(sender_details.get("full_name") or sender_details.get("user") or "")
    mobile = sender_details.get("mobile")
    return f"""
        <h2>Statement of Account</h2>
        <p><strong>Customer:</strong> {safe_name}</p>
        <p>Please find attached your current Statement of Account.</p>
        <p><a href="{soa_url}">View Online Statement</a></p>
        <hr>
        <p><small>Sent by: {sender_line}{(' • ' + mobile) if mobile else ''}</small></p>
    """


def _generate_overdue_email_body(customer_name: str, overdue_data: dict, sender_details: dict) -> str:
    """HTML body for Overdue notice."""
    safe_name = frappe.utils.escape_html(customer_name)
    fn = frappe.utils.escape_html(sender_details.get("full_name") or sender_details.get("user") or "")
    mobile = sender_details.get("mobile") or ""
    return f"""
        <div style="background-color:#fef2f2;padding:20px;border-left:4px solid #ef4444;">
            <h2 style="color:#ef4444;">🔴 Payment Overdue Notice</h2>
            <p><strong>Dear {safe_name},</strong></p>
            <p>There is an outstanding balance on your account that requires immediate attention.</p>
            <h3>Account Summary</h3>
            <table style="width:100%;border-collapse:collapse;">
                <tr>
                    <td style="padding:10px;border:1px solid #e5e7eb;"><strong>Total Overdue</strong></td>
                    <td style="padding:10px;border:1px solid #e5e7eb;text-align:right;">
                        <strong>{frappe.utils.fmt_money(overdue_data['total_overdue'])}</strong>
                    </td>
                </tr>
                <tr>
                    <td style="padding:10px;border:1px solid #e5e7eb;">Total Outstanding</td>
                    <td style="padding:10px;border:1px solid #e5e7eb;text-align:right;">
                        {frappe.utils.fmt_money(overdue_data['total_outstanding'])}
                    </td>
                </tr>
            </table>
            <h3>Aging</h3>
            <table style="width:100%;border-collapse:collapse;">
                <tr><td style="padding:8px;border:1px solid #e5e7eb;">0-30 Days</td>
                    <td style="padding:8px;border:1px solid #e5e7eb;text-align:right;">
                        {frappe.utils.fmt_money(overdue_data['outstanding_0_30'])}
                    </td></tr>
                <tr><td style="padding:8px;border:1px solid #e5e7eb;">31-60 Days</td>
                    <td style="padding:8px;border:1px solid #e5e7eb;text-align:right;">
                        {frappe.utils.fmt_money(overdue_data['outstanding_31_60'])}
                    </td></tr>
                <tr><td style="padding:8px;border:1px solid #e5e7eb;">61-90 Days</td>
                    <td style="padding:8px;border:1px solid #e5e7eb;text-align:right;">
                        {frappe.utils.fmt_money(overdue_data['outstanding_61_90'])}
                    </td></tr>
                <tr><td style="padding:8px;border:1px solid #e5e7eb;">Over 90 Days</td>
                    <td style="padding:8px;border:1px solid #e5e7eb;text-align:right;">
                        {frappe.utils.fmt_money(overdue_data['outstanding_over_90'])}
                    </td></tr>
            </table>
            <p style="margin-top:16px;">Please settle the balance to avoid disruption of services.</p>
            <hr>
            <p><small>Sent by: {fn}{(' • ' + mobile) if mobile else ''}</small></p>
        </div>
    """


def _generate_aging_analysis_pdf(customer_name: str) -> bytes:
    """Generate a simple Aging Analysis PDF (template if available, fallback otherwise)."""
    try:
        html = frappe.render_template("templates/emails/aging_analysis.html", {
            "customer_name": customer_name,
            "aging_data": _calculate_overdue_details(customer_name),
            "money": frappe.utils.fmt_money,
        })
    except Exception:
        data = _calculate_overdue_details(customer_name)
        html = f"""
            <h2>Aging Analysis - {frappe.utils.escape_html(customer_name)}</h2>
            <ul>
                <li>0-30 Days: {frappe.utils.fmt_money(data['outstanding_0_30'])}</li>
                <li>31-60 Days: {frappe.utils.fmt_money(data['outstanding_31_60'])}</li>
                <li>61-90 Days: {frappe.utils.fmt_money(data['outstanding_61_90'])}</li>
                <li>Over 90 Days: {frappe.utils.fmt_money(data['outstanding_over_90'])}</li>
            </ul>
        """
    return get_pdf(html)


def _log_communication(recipients: list[str], subject: str, doctype: str, name: str, notes: str = ""):
    """Write a Communication row; ignore perms for audit trail."""
    all_recipients = ", ".join([r for r in recipients if r and "@" in r])
    frappe.get_doc({
        "doctype": "Communication",
        "communication_type": "Communication",
        "content": f"Email sent: {frappe.utils.escape_html(subject)}<br>Recipients: {frappe.utils.escape_html(all_recipients)}"
                   + (f"<br>{frappe.utils.escape_html(notes)}" if notes else ""),
        "reference_doctype": doctype,
        "reference_name": name,
        "sent_or_received": "Sent",
        "status": "Completed"
    }).insert(ignore_permissions=True)
    
@contextmanager
def _privileged_print_format_queries():
	"""Print Format Jinja uses ``frappe.get_list``; mobile users lack SI read role."""
	orig_list = frappe.get_list
	orig_all = frappe.get_all

	def get_list(doctype, *args, **kwargs):
		kwargs["ignore_permissions"] = True
		return orig_list(doctype, *args, **kwargs)

	def get_all(doctype, *args, **kwargs):
		kwargs["ignore_permissions"] = True
		return orig_all(doctype, *args, **kwargs)

	frappe.get_list = get_list
	frappe.get_all = get_all
	try:
		yield
	finally:
		frappe.get_list = orig_list
		frappe.get_all = orig_all


def _soa_html_has_body(html: str | None) -> bool:
	return bool(html and "Statement Of Account" in html)


def _count_outstanding_soa_invoices(customer_name: str) -> int:
	"""Same threshold as Print Format ``Customer Outstanding SOA`` (outstanding > 10)."""
	return frappe.db.count(
		"Sales Invoice",
		{
			"docstatus": 1,
			"customer": customer_name,
			"outstanding_amount": (">", 10),
		},
	)


def _render_soa_print_html(doc, print_format: str, *, privileged: bool) -> str:
	"""Render desk SOA print format; ``privileged`` uses desk-equivalent data after API + territory checks."""
	if not privileged:
		doc.check_permission("print")
		return frappe.get_print(doc=doc, print_format=print_format)

	# Mobile users lack Customer print + Sales Invoice read; render exactly as desk (Administrator).
	session_user = frappe.session.user
	try:
		frappe.set_user("Administrator")
		admin_doc = frappe.get_doc("Customer", doc.name)
		return frappe.get_print(doc=admin_doc, print_format=print_format)
	finally:
		frappe.set_user(session_user)


def _generate_customer_soa_pdf(
    customer_name: str,
    company: str | None = None,
    print_format: str | None = None,
    *,
    profile_governed: bool = False,
    privileged_soa_render: bool = False,
) -> tuple[bytes, str, dict]:
    """Generate Statement of Account PDF (same as desk Print → Customer Outstanding SOA).

    Outstanding invoice lines are not filtered by API ``from_date`` / ``to_date``.
    When ``profile_governed`` is False (desk / email path), normal Customer ``print`` permission applies.
    Returns (pdf_bytes, filename).
    """
    _ = company  # reserved for future multi-company print context
    print_format = print_format or SOA_PRINT_FORMAT
    doc = frappe.get_doc("Customer", customer_name)
    privileged = bool(privileged_soa_render or profile_governed)
    html = _render_soa_print_html(doc, print_format, privileged=privileged)
    meta = {
        "soa_body_present": _soa_html_has_body(html),
        "outstanding_invoice_count": _count_outstanding_soa_invoices(customer_name),
        "soa_render_privileged": privileged,
    }
    if privileged and not meta["soa_body_present"] and meta["outstanding_invoice_count"]:
        frappe.log_error(
            title="SOA PDF empty body",
            message=f"customer={customer_name} invoices={meta['outstanding_invoice_count']}",
        )
        frappe.throw(
            _("Statement PDF could not be generated (desk SOA data missing). Contact IT."),
            frappe.ValidationError,
        )

    pdf = get_pdf(html)
    safe_name = frappe.scrub(customer_name).replace("-", "_")
    filename = f"Statement_of_Account_{safe_name}.pdf"
    return pdf, filename, meta

