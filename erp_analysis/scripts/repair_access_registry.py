"""Desk/ops: repair AO- series + seed full mobile API registry (safe to re-run)."""

from __future__ import annotations

import frappe

from erp_analysis.patches.sync_mobile_access_registry import execute as sync_registry_execute


def run():
	"""bench --site SITE execute erp_analysis.scripts.repair_access_registry.run"""
	return sync_registry_execute()
