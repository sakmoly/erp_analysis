import frappe
from frappe.model.document import Document


class MobilePushToken(Document):
    def before_save(self):
        self.last_seen = frappe.utils.now_datetime()

