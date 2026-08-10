import frappe
from frappe.model.document import Document

from erp_analysis.permissions.access_profile import clear_caches


class AccessProfile(Document):
	def before_insert(self):
		# Ensure new profiles start with the full active registry
		if not self.access_rules:
			for row in get_default_access_rule_rows():
				self.append("access_rules", row)

	def validate(self):
		if not self.enabled:
			return
		if not self.access_rules:
			frappe.throw("Add at least one child rule.")

	def on_update(self):
		clear_caches(user=self.user)

	def on_trash(self):
		clear_caches(user=self.user)


def get_default_access_rule_rows() -> list[dict]:
	"""All active Access Object Registry entries as Access Profile Line defaults."""
	objects = frappe.get_all(
		"Access Object Registry",
		filters={"is_active": 1},
		fields=["name", "object_type", "label", "object_key"],
		order_by="object_type asc, label asc",
		limit_page_length=10000,
	)
	rows = []
	for idx, obj in enumerate(objects, start=1):
		rows.append(
			{
				"sequence": idx,
				"access_object": obj.name,
				"object_type": obj.object_type,
				"label": obj.label,
				"can_view": 0,
				"can_approve": 0,
				"can_export": 0,
				"can_create": 0,
				"can_edit": 0,
				"active": 1,
			}
		)
	return rows


@frappe.whitelist()
def get_default_access_rules():
	"""Called from Access Profile form (new doc / Load All button)."""
	return get_default_access_rule_rows()


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def access_object_link_query(doctype, txt, searchfield, start, page_len, filters):
	"""Return active Access Object Registry rows (full list, not capped at 10)."""
	txt = (txt or "").strip()
	conds = ["ifnull(is_active, 0) = 1"]
	try:
		start_i = int(start or 0)
	except Exception:
		start_i = 0
	try:
		page_i = int(page_len or 50)
	except Exception:
		page_i = 50
	page_i = max(page_i, 500)

	values = {"start": start_i, "page_len": page_i}
	if txt:
		conds.append(
			"(name like %(txt)s or label like %(txt)s or object_key like %(txt)s or object_type like %(txt)s)"
		)
		values["txt"] = f"%{txt}%"

	where = " and ".join(conds)
	return frappe.db.sql(
		f"""
		select name, concat(ifnull(label, name), ' (', ifnull(object_type, ''), ')') as description
		from `tabAccess Object Registry`
		where {where}
		order by object_type asc, label asc
		limit %(start)s, %(page_len)s
		""",
		values,
	)
