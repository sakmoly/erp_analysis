"""Grant VAT dashboard API on a user's Access Profile."""

from __future__ import annotations

import frappe

from erp_analysis.permissions.access_profile import clear_caches
from erp_analysis.tax import VAT_API_OBJECT

SOA_OBJECT_KEYS = (
	"erp_analysis.customer_notifications.get_statement_pdf",
	"erp_analysis.customer_notifications.get_statement_branding",
	"erp_analysis.customer_notifications.send_statement_pdf",
	"erp_analysis.receivables.get_statement_branding",
	"erp_analysis.receivables.get_customer_statement",
	"printechs_utility.customer_notifications.get_statement_pdf",
	"printechs_utility.customer_notifications.get_statement_branding",
	"printechs_utility.customer_notifications.send_statement_pdf",
)


def _grant_object_keys(profile, object_keys: tuple[str, ...]) -> bool:
	from erp_analysis.permissions.access_profile import clear_caches

	changed = False
	for object_key in object_keys:
		registry_name = frappe.db.get_value(
			"Access Object Registry", {"object_key": object_key}, "name"
		)
		if not registry_name:
			continue
		existing = next(
			(row for row in profile.access_rules or [] if row.access_object == registry_name),
			None,
		)
		if existing:
			if not existing.can_view:
				existing.can_view = 1
				changed = True
		else:
			profile.append(
				"access_rules",
				{"access_object": registry_name, "can_view": 1, "can_approve": 0},
			)
			changed = True
	clear_caches(user=profile.user)
	return changed


def grant_soa_mobile(user: str = "sakeer@printechs.com", company: str | None = None) -> dict:
	filters: dict = {"user": user, "enabled": 1}
	if company:
		filters["company"] = company
	profile_name = frappe.db.get_value("Access Profile", filters, "name")
	if not profile_name:
		profile_name = frappe.db.get_value("Access Profile", {"user": user, "enabled": 1}, "name")
	if not profile_name:
		frappe.throw(f"No enabled Access Profile for user {user}")
	profile = frappe.get_doc("Access Profile", profile_name)
	changed = _grant_object_keys(profile, SOA_OBJECT_KEYS)
	if changed:
		profile.save(ignore_permissions=True)
	frappe.db.commit()
	return {"ok": True, "user": user, "access_profile": profile_name, "changed": changed}


def grant(user: str = "sakeer@printechs.com", company: str | None = None) -> dict:
	registry_name = frappe.db.get_value(
		"Access Object Registry", {"object_key": VAT_API_OBJECT}, "name"
	)
	if not registry_name:
		frappe.throw(f"Registry missing for {VAT_API_OBJECT}")

	filters: dict = {"user": user, "enabled": 1}
	if company:
		filters["company"] = company
	profile_name = frappe.db.get_value("Access Profile", filters, "name")
	if not profile_name:
		profile_name = frappe.db.get_value("Access Profile", {"user": user, "enabled": 1}, "name")
	if not profile_name:
		frappe.throw(f"No enabled Access Profile for user {user}")

	profile = frappe.get_doc("Access Profile", profile_name)
	existing = next(
		(row for row in profile.access_rules or [] if row.access_object == registry_name),
		None,
	)
	changed = False
	if existing:
		if not existing.can_view:
			existing.can_view = 1
			changed = True
	else:
		profile.append(
			"access_rules",
			{
				"access_object": registry_name,
				"can_view": 1,
				"can_approve": 0,
			},
		)
		changed = True

	if changed:
		profile.save(ignore_permissions=True)

	frappe.db.commit()
	clear_caches(user=user)

	frappe.set_user(user)
	from erp_analysis.access_context import require_object_access

	try:
		require_object_access(VAT_API_OBJECT, user=user, company=company or profile.company)
		access = "allowed"
	except Exception as exc:
		access = str(exc)

	return {
		"ok": True,
		"user": user,
		"access_profile": profile_name,
		"registry": registry_name,
		"changed": changed,
		"object_access": access,
	}
