"""Internal QA for mobile SOA PDF — run:

bench --site site1.local execute erp_analysis.scripts.test_soa_pdf_internal.run
"""

from __future__ import annotations

import base64
import json
import subprocess

import frappe


def run(
	user: str = "sakeer@printechs.com",
	company: str = "Printechs Advanced Printing Trading Co.",
	customers: list[str] | None = None,
) -> dict:
	from erp_analysis.customer_notifications import get_statement_pdf

	customers = customers or ["LANDMARK ARABIA CO.", "USG Middle East Ltd."]
	frappe.set_user(user)
	results = []

	for customer_name in customers:
		frappe.form_dict.clear()
		frappe.form_dict.update(
			{
				"customer_name": customer_name,
				"company": company,
				"return_pdf": 1,
				"return_file_url": 1,
				"print_format": "Customer Outstanding SOA",
			}
		)
		row: dict = {"customer_name": customer_name, "ok": False}
		try:
			resp = get_statement_pdf()
			msg = resp.get("message") or resp
			row["soa_body_present"] = msg.get("soa_body_present")
			row["outstanding_invoice_count"] = msg.get("outstanding_invoice_count")
			row["file_url"] = msg.get("file_url")
			b64 = msg.get("pdf_base64")
			if b64:
				raw = base64.b64decode(b64)
				row["pdf_bytes"] = len(raw)
				txt = subprocess.check_output(
					["pdftotext", "-", "-"], input=raw, stderr=subprocess.DEVNULL
				).decode(errors="ignore")
				row["pdf_has_statement_heading"] = "Statement Of Account" in txt
				row["pdf_invoice_line_hint"] = txt.count("SIR") + txt.count("SID")
			row["ok"] = bool(
				row.get("soa_body_present")
				and row.get("pdf_has_statement_heading")
				and (row.get("outstanding_invoice_count") or 0) >= 0
			)
		except Exception as exc:
			row["error"] = f"{type(exc).__name__}: {exc}"
		results.append(row)

	summary = {
		"user": user,
		"company": company,
		"all_ok": all(r.get("ok") for r in results),
		"results": results,
	}
	print(json.dumps(summary, indent=2))
	return summary
