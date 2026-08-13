# Copyright (c) 2026, ERP Analysis Contributors

import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import patch

from erp_analysis.services.mobile_bootstrap import build_mobile_bootstrap
from erp_analysis.services.mobile_profile import (
	get_profile_dimensions_public,
	get_profile_modules,
	resolve_mobile_app_profile_name,
)


class TestBootstrapProfiles(FrappeTestCase):
	"""Phase I — profile shape tests using temporary docs (rolled back after test)."""

	PROFILE_PREFIX = "__TEST_MOBILE_PROFILE__"

	def tearDown(self):
		for name in frappe.get_all("Mobile App Profile", pluck="name", filters={"name": ["like", f"{self.PROFILE_PREFIX}%"]}):
			frappe.delete_doc("Mobile App Profile", name, force=1, ignore_permissions=True)
		super().tearDown()

	def _create_profile(self, profile_name: str, business_type: str, modules: list[str], dimensions: list[str]):
		dimension_field_map = {
			"territory": ("Sales Invoice", "territory"),
			"company": ("Sales Invoice", "company"),
			"brand": ("Sales Invoice Item", "brand"),
			"warehouse": ("Sales Invoice Item", "warehouse"),
		}
		dimension_rows = []
		for key in dimensions:
			doctype, field = dimension_field_map.get(key, ("Sales Invoice", "territory"))
			from erp_analysis.utils.schema import has_field

			if not has_field(doctype, field):
				continue
			dimension_rows.append(
				{
					"dimension_key": key,
					"label": key.title(),
					"enabled": 1,
					"source_doctype": doctype,
					"source_field": field,
					"source_mode": "FIELD",
					"allow_filter": 1,
					"allow_group_by": 1,
				}
			)

		doc = frappe.get_doc(
			{
				"doctype": "Mobile App Profile",
				"profile_name": profile_name,
				"business_type": business_type,
				"enabled": 1,
				"app_title": profile_name,
				"modules": [
					{"module_key": key, "label": key.title(), "enabled": 1, "sort_order": idx}
					for idx, key in enumerate(modules)
				],
				"dimensions": dimension_rows,
			}
		)
		doc.insert(ignore_permissions=True)
		return doc.name

	def test_b2b_fashion_supermarket_different_module_lists(self):
		b2b = self._create_profile(
			f"{self.PROFILE_PREFIX}-B2B",
			"B2B",
			["sales", "receivables", "inventory", "customer_360"],
			["territory", "company"],
		)
		fashion = self._create_profile(
			f"{self.PROFILE_PREFIX}-FASHION",
			"FASHION_RETAIL",
			["sales", "sales_performance", "inventory"],
			["territory"],
		)
		market = self._create_profile(
			f"{self.PROFILE_PREFIX}-SUPER",
			"SUPERMARKET",
			["sales", "inventory", "purchase"],
			["territory", "company"],
		)

		b2b_modules = {m["key"] for m in get_profile_modules(b2b)}
		fashion_modules = {m["key"] for m in get_profile_modules(fashion)}
		market_modules = {m["key"] for m in get_profile_modules(market)}

		self.assertIn("customer_360", b2b_modules)
		self.assertNotIn("customer_360", fashion_modules)
		self.assertIn("purchase", market_modules)
		self.assertNotIn("purchase", fashion_modules)

		b2b_dims = {d["key"] for d in get_profile_dimensions_public(b2b)}
		fashion_dims = {d["key"] for d in get_profile_dimensions_public(fashion)}
		self.assertIn("company", b2b_dims)
		self.assertNotIn("company", fashion_dims)

	def test_bootstrap_ignores_client_profile_name(self):
		"""Profile is server-resolved only — no client-supplied profile parameter."""
		test_name = self._create_profile(
			f"{self.PROFILE_PREFIX}-BOOT",
			"B2B",
			["sales"],
			["territory"],
		)
		with patch(
			"erp_analysis.services.mobile_bootstrap.resolve_mobile_app_profile_name",
			return_value=test_name,
		):
			payload = build_mobile_bootstrap(user=frappe.session.user)
		self.assertEqual(payload["context"].get("profile"), test_name)
		self.assertEqual(payload["schema_version"], 1)

	def test_resolve_none_without_profile_link(self):
		with patch(
			"erp_analysis.services.mobile_profile._get_user_profile_name",
			return_value=None,
		), patch(
			"erp_analysis.services.mobile_profile._read_settings_default_profile",
			return_value=None,
		):
			self.assertIsNone(resolve_mobile_app_profile_name(user=frappe.session.user))

	def test_disabled_profile_not_resolved(self):
		from erp_analysis.services.mobile_profile import _profile_is_active

		name = self._create_profile(
			f"{self.PROFILE_PREFIX}-DISABLED",
			"B2B",
			["sales"],
			["territory"],
		)
		frappe.db.set_value("Mobile App Profile", name, "enabled", 0)
		self.assertFalse(_profile_is_active(name))
		with patch(
			"erp_analysis.services.mobile_profile._get_user_profile_name",
			return_value=None,
		), patch(
			"erp_analysis.services.mobile_profile._read_settings_default_profile",
			return_value=None,
		):
			self.assertIsNone(resolve_mobile_app_profile_name(user=frappe.session.user))
