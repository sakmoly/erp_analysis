import frappe
from frappe.model.document import Document

from erp_analysis.mobile_config import clear_mobile_config_cache


class MobileAppSettings(Document):
	def on_update(self):
		clear_mobile_config_cache()
