import frappe
from frappe import _
from frappe.model.document import Document

from erp_analysis.mobile_config import clear_mobile_config_cache


class MobileAppProfile(Document):
	def validate(self):
		self._validate_unique_profile_name()
		self._validate_child_rows()

	def on_update(self):
		clear_mobile_config_cache()

	def on_trash(self):
		clear_mobile_config_cache()

	def _validate_unique_profile_name(self):
		name = (self.profile_name or "").strip()
		if not name:
			frappe.throw(_("Profile Name is required"))
		existing = frappe.db.get_value(
			"Mobile App Profile",
			{"profile_name": name, "name": ["!=", self.name]},
			"name",
		)
		if existing:
			frappe.throw(_("Profile Name must be unique"))

	def _validate_child_rows(self):
		from erp_analysis.services.mobile_dimensions import validate_dimension_definition

		seen_modules: set[str] = set()
		for row in self.modules or []:
			key = (row.module_key or "").strip().lower()
			if not key:
				frappe.throw(_("Module Key is required on all module rows"))
			if key in seen_modules:
				frappe.throw(_("Duplicate module key: {0}").format(key))
			seen_modules.add(key)

		seen_dimensions: set[str] = set()
		for row in self.dimensions or []:
			key = (row.dimension_key or "").strip().lower()
			if not key:
				frappe.throw(_("Dimension Key is required on all dimension rows"))
			if key in seen_dimensions:
				frappe.throw(_("Duplicate dimension key: {0}").format(key))
			seen_dimensions.add(key)
			validate_dimension_definition(row)

		seen_widgets: set[str] = set()
		for row in self.dashboard_widgets or []:
			key = (row.widget_key or "").strip().lower()
			if not key:
				frappe.throw(_("Widget Key is required on all dashboard widget rows"))
			if key in seen_widgets:
				frappe.throw(_("Duplicate widget key: {0}").format(key))
			seen_widgets.add(key)
