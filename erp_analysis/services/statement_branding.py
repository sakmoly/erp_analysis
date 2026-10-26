"""SOA letterhead + payment footer for mobile HTML/PDF (aligned with Customer Outstanding SOA)."""

from __future__ import annotations

import re
from typing import Any, Optional

import frappe
from frappe.contacts.doctype.address.address import get_default_address
from frappe.utils import strip_html

from erp_analysis.utils.rpc import absolute_file_url

SOA_PRINT_FORMAT = "Customer Outstanding SOA"


def _compact_iban(iban: str) -> str:
	return re.sub(r"\s+", "", (iban or "").strip())


def _resolve_bank_from_soa_print_format() -> dict[str, Any]:
	"""Desk SOA hard-codes payment footer in ``Customer Outstanding SOA`` — mobile must match."""
	html = frappe.db.get_value("Print Format", SOA_PRINT_FORMAT, "html") or ""
	if not html:
		return {}

	def _extract(label: str) -> str:
		font_pat = rf"{label}\s*:.*?<font[^>]*>(.*?)</font>"
		m = re.search(font_pat, html, re.IGNORECASE | re.DOTALL)
		if m:
			return strip_html(m.group(1)).strip()
		plain_pat = rf"{label}\s*:([^<\n]+)"
		m = re.search(plain_pat, html, re.IGNORECASE)
		return strip_html(m.group(1)).strip() if m else ""

	company_line = _extract("Company")
	account_no = _extract("Account")
	bank = _extract("Bank")
	iban_raw = _extract("IBAN")
	if not any([company_line, account_no, bank, iban_raw]):
		return {}

	return {
		"source": "print_format",
		"footer_company_line": company_line,
		"bank_account_name": company_line,
		"bank": bank,
		"iban": _compact_iban(iban_raw),
		"account_no": account_no,
	}


def _resolve_bank_from_company(company: str) -> dict[str, Any]:
	bank_name = frappe.db.get_value("Company", company, "default_bank_account")
	row: dict[str, Any] = {}
	if bank_name and frappe.db.exists("Bank Account", bank_name):
		ba = frappe.get_doc("Bank Account", bank_name)
		row = {
			"source": "company_default_bank_account",
			"bank_account_name": ba.account_name or bank_name,
			"bank": ba.bank or "",
			"iban": _compact_iban(ba.iban or ""),
			"account_no": ba.bank_account_no or "",
		}
	if not row.get("iban"):
		fallback = frappe.db.sql(
			"""
			SELECT account_name, bank, iban, bank_account_no
			FROM `tabBank Account`
			WHERE company = %s AND disabled = 0 AND IFNULL(iban, '') != ''
			ORDER BY modified DESC
			LIMIT 1
			""",
			company,
			as_dict=True,
		)
		if fallback:
			ba = fallback[0]
			row = {
				"source": "company_latest_iban",
				"bank_account_name": ba.account_name,
				"bank": ba.bank or "",
				"iban": _compact_iban(ba.iban or ""),
				"account_no": ba.bank_account_no or "",
			}
	return row


def _resolve_bank_details(company: str) -> dict[str, Any]:
	from_print = _resolve_bank_from_soa_print_format()
	if from_print.get("iban") or from_print.get("account_no"):
		return from_print
	return _resolve_bank_from_company(company)


def _company_address_html(company: str) -> str:
	addr_name = get_default_address("Company", company)
	if not addr_name:
		return ""
	addr = frappe.get_doc("Address", addr_name)
	lines = [
		addr.address_line1,
		addr.address_line2,
		addr.city,
		addr.state,
		addr.pincode,
		addr.country,
	]
	parts = [frappe.utils.escape_html(x) for x in lines if x]
	return "<br>".join(parts)


def build_statement_branding(
	company: Optional[str] = None,
	customer: Optional[str] = None,
) -> dict[str, Any]:
	"""Branding block for mobile SOA HTML (header/footer) and PDF metadata."""
	company = company or frappe.defaults.get_user_default("Company")
	if not company or not frappe.db.exists("Company", company):
		frappe.throw("Company is required")

	co = frappe.get_doc("Company", company)
	bank = _resolve_bank_details(company)
	address_html = _company_address_html(company)

	logo_url = ""
	if co.company_logo:
		logo_url = absolute_file_url(co.company_logo)

	letter_head_html = ""
	letter_footer_html = ""
	lh_name = co.default_letter_head
	if not lh_name:
		lh_name = frappe.db.get_value("Letter Head", {"disabled": 0, "is_default": 1}, "name")
	if lh_name and frappe.db.exists("Letter Head", lh_name):
		lh = frappe.get_doc("Letter Head", lh_name)
		letter_head_html = lh.content or ""
		letter_footer_html = lh.footer or ""
		if lh.image and not logo_url:
			logo_url = absolute_file_url(lh.image)

	ctx = {
		"company_name": co.company_name or company,
		"company": company,
		"customer": customer,
		"tax_id": co.tax_id or "",
		"phone": co.phone_no or "",
		"email": co.email or "",
		"website": co.website or "",
		"address_html": address_html,
		"logo_url": logo_url,
		"bank": bank,
		"print_format": SOA_PRINT_FORMAT,
	}

	header_html = letter_head_html.strip()
	if not header_html:
		header_html = frappe.render_template(
			"""
<div style="font-family:Arial,Helvetica,sans-serif;border-bottom:2px solid #1f4e79;padding-bottom:10px;margin-bottom:12px;">
  <table style="width:100%;border-collapse:collapse;">
    <tr>
      {% if logo_url %}
      <td style="width:80px;vertical-align:top;">
        <img src="{{ logo_url }}" alt="logo" style="max-width:72px;max-height:72px;" />
      </td>
      {% endif %}
      <td style="vertical-align:top;">
        <div style="font-size:18px;font-weight:bold;color:#1f4e79;">{{ company_name }}</div>
        {% if address_html %}<div style="font-size:12px;color:#444;margin-top:4px;">{{ address_html }}</div>{% endif %}
        {% if tax_id %}<div style="font-size:12px;color:#444;margin-top:4px;">VAT: {{ tax_id }}</div>{% endif %}
      </td>
      <td style="text-align:right;vertical-align:top;">
        <div style="font-size:16px;font-weight:bold;color:#1f4e79;text-transform:uppercase;">Statement of Account</div>
      </td>
    </tr>
  </table>
</div>
			""".strip(),
			ctx,
		)

	payment_note = (
		"If you have already made payment of any of the above invoices, please revert with payment "
		"details to our Accounts Dept. so we can update our record accordingly."
	)
	second_note = (
		"If you haven't paid, please process payment as soon as possible. Bank details:"
	)

	footer_company = bank.get("footer_company_line") or ctx["company_name"]
	footer_lines: list[str] = []
	if footer_company or bank.get("account_no"):
		footer_lines.append(f"Company :{footer_company}")
	if bank.get("account_no"):
		footer_lines.append(f"Account :{bank['account_no']}")
	if bank.get("bank"):
		footer_lines.append(f"Bank :{bank['bank']}")
	if bank.get("iban"):
		footer_lines.append(f"IBAN :{bank['iban']}")

	footer_html = letter_footer_html.strip()
	if not footer_html:
		footer_html = frappe.render_template(
			"""
<div style="font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#222;margin-top:16px;page-break-inside:avoid;">
  <p style="margin:0 0 8px 0;">{{ payment_note }}</p>
  <p style="margin:0 0 8px 0;">{{ second_note }}</p>
  <table style="width:100%;border-collapse:collapse;margin-top:6px;">
    {% for line in footer_lines %}
    <tr><td style="padding:2px 0;">{{ line }}</td></tr>
    {% endfor %}
  </table>
  <p style="margin:12px 0 0 0;color:#666;font-size:11px;">
    This statement is generated for customer reference. Print format: {{ print_format }}.
  </p>
</div>
			""".strip(),
			{**ctx, "payment_note": payment_note, "second_note": second_note, "footer_lines": footer_lines},
		)

	return {
		"company_name": ctx["company_name"],
		"company": company,
		"company_address_html": address_html,
		"logo_url": logo_url,
		"tax_id": ctx["tax_id"],
		"header_html": header_html,
		"footer_html": footer_html,
		"footer_lines": footer_lines,
		"print_format": SOA_PRINT_FORMAT,
		"bank": bank,
	}


def wrap_mobile_message(payload: dict[str, Any]) -> dict[str, Any]:
	"""Expose both Frappe-style message wrapper and top-level keys for mobile clients."""
	out = dict(payload)
	out["message"] = dict(payload)
	return out
