"""Smoke test VAT API as a given user."""

from __future__ import annotations

import json

import frappe

from erp_analysis.tax import get_vat_dashboard


def run(user: str = "sakeer@printechs.com") -> None:
	frappe.set_user(user)
	company = frappe.db.get_value("Access Profile", {"user": user, "enabled": 1}, "company")
	out = get_vat_dashboard(company=company, period="mtd")
	print(json.dumps({"user": user, "company": company, "net_vat_due": out["submitted"]["net_vat_due"]}, indent=2))
