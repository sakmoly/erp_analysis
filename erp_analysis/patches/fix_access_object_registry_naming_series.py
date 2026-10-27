"""One-time: fix AO- series counter when registry sync fails with DuplicateEntryError."""

from erp_analysis.patches.sync_mobile_access_registry import (
	ensure_registry_rows,
	sync_access_object_registry_naming_series,
	sync_access_profiles,
)
from erp_analysis.permissions.access_profile import clear_caches

import frappe


def execute():
	if not frappe.db.exists("DocType", "Access Object Registry"):
		return
	sync_access_object_registry_naming_series()
	key_to_name = ensure_registry_rows()
	added = sync_access_profiles(key_to_name)
	frappe.db.commit()
	clear_caches()
	return {"series_current": sync_access_object_registry_naming_series(), "registry_keys": len(key_to_name), "profile_lines_added": added}
