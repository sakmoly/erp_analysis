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
		try:
			from erp_analysis.services.mobile_widgets import clear_dashboard_board_cache

			clear_dashboard_board_cache()
		except Exception:
			pass

	def on_trash(self):
		clear_mobile_config_cache()
		try:
			from erp_analysis.services.mobile_widgets import clear_dashboard_board_cache

			clear_dashboard_board_cache()
		except Exception:
			pass

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

		def _val(row, field: str):
			if isinstance(row, dict):
				return row.get(field)
			return getattr(row, field, None)

		seen_modules: set[str] = set()
		for row in self.modules or []:
			key = (_val(row, "module_key") or "").strip().lower()
			if not key:
				frappe.throw(_("Module Key is required on all module rows"))
			if key in seen_modules:
				frappe.throw(_("Duplicate module key: {0}").format(key))
			seen_modules.add(key)
			screen_type = (_val(row, "screen_type") or "module").strip().lower()
			if screen_type == "dashboard":
				board_id = (_val(row, "dashboard_id") or _val(row, "module_key") or "").strip().lower()
				if not board_id:
					frappe.throw(_("Dashboard ID is required when Screen Type is dashboard (module {0})").format(key))

		seen_dimensions: set[str] = set()
		for row in self.dimensions or []:
			key = (_val(row, "dimension_key") or "").strip().lower()
			if not key:
				frappe.throw(_("Dimension Key is required on all dimension rows"))
			if key in seen_dimensions:
				frappe.throw(_("Duplicate dimension key: {0}").format(key))
			seen_dimensions.add(key)
			validate_dimension_definition(row)

		seen_widgets: set[str] = set()
		seen_dashboards: set[str] = set()
		for row in self.dashboards or []:
			key = (_val(row, "dashboard_key") or "").strip().lower()
			if not key:
				frappe.throw(_("Dashboard Key is required on all dashboard board rows"))
			if key in seen_dashboards:
				frappe.throw(_("Duplicate dashboard key: {0}").format(key))
			seen_dashboards.add(key)

		default_board = (self.default_dashboard or "home").strip().lower()
		if seen_dashboards and default_board and default_board not in seen_dashboards:
			frappe.throw(_("Default Dashboard {0} is not defined in Dashboard Boards").format(self.default_dashboard))

		for row in self.dashboard_widgets or []:
			key = (_val(row, "widget_key") or "").strip().lower()
			if not key:
				frappe.throw(_("Widget Key is required on all dashboard widget rows"))
			if key in seen_widgets:
				frappe.throw(_("Duplicate widget key: {0}").format(key))
			seen_widgets.add(key)
			board_id = (_val(row, "dashboard_id") or default_board or "home").strip().lower()
			if seen_dashboards and board_id not in seen_dashboards:
				frappe.throw(
					_("Widget {0} references unknown dashboard_id: {1}").format(
						_val(row, "widget_key"), _val(row, "dashboard_id")
					)
				)

		for row in self.modules or []:
			screen_type = (_val(row, "screen_type") or "module").strip().lower()
			if screen_type != "dashboard":
				continue
			if not _val(row, "enabled"):
				continue
			board_id = (_val(row, "dashboard_id") or _val(row, "module_key") or "").strip().lower()
			if seen_dashboards and board_id and board_id not in seen_dashboards:
				frappe.throw(
					_("Module {0} references unknown dashboard board: {1}").format(
						_val(row, "module_key"), board_id
					)
				)
