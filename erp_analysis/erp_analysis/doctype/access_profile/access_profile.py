import frappe
from frappe.model.document import Document

from erp_analysis.permissions.access_profile import clear_caches


class AccessProfile(Document):
	def validate(self):
		if not self.enabled:
			return
		if not self.access_rules:
			frappe.throw("Add at least one child rule.")

	def on_update(self):
		clear_caches(user=self.user)

	def on_trash(self):
		clear_caches(user=self.user)
