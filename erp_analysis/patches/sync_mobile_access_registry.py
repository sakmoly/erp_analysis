"""Canonical mobile API registry + Access Profile sync."""

from __future__ import annotations

import frappe

from erp_analysis.permissions.access_profile import clear_caches

# object_key, label
MOBILE_API_REGISTRY: tuple[tuple[str, str], ...] = (
	# Dashboard / sales home
	("erp_analysis.dashboard.get_complete_dashboard_data", "Complete Dashboard"),
	("erp_analysis.dashboard.get_executive_dashboard", "Executive Dashboard (dashboard alias)"),
	("erp_analysis.executive.get_executive_dashboard", "Executive Dashboard"),
	("erp_analysis.sales_kpis.get_dashboard_kpis", "Dashboard KPIs"),
	("erp_analysis.sales_kpis.get_sales_dashboard", "Sales Dashboard"),
	# Sales performance
	("erp_analysis.sales_performance.get_salesperson_ranking", "Salesperson Ranking"),
	("erp_analysis.sales_performance.get_product_ranking", "Product Ranking"),
	("erp_analysis.sales_performance.get_salesperson_performance", "Salesperson Performance"),
	("erp_analysis.sales_performance.get_product_performance", "Product Performance"),
	("erp_analysis.sales.get_salesperson_performance", "Salesperson Performance (sales alias)"),
	("erp_analysis.sales.get_product_performance", "Product Performance (sales alias)"),
	# Customer (mobile contract paths)
	("erp_analysis.customer.search_customers", "Customer Search"),
	("erp_analysis.customer.get_customer_360", "Customer 360 (mobile path)"),
	("erp_analysis.sales_kpis.get_salesperson_performance", "Salesperson Performance (sales_kpis alias)"),
	("erp_analysis.sales_kpis.get_product_performance", "Product Performance (sales_kpis alias)"),
	# Collection
	("erp_analysis.collection.get_collection_dashboard", "Collection Dashboard"),
	("erp_analysis.collection.get_collection_attention", "Collection Attention"),
	# Receivables
	("erp_analysis.receivables.get_receivables_snapshot", "Receivables Snapshot"),
	("erp_analysis.receivables.get_receivables_performance", "Receivables Performance"),
	("erp_analysis.receivables.get_receivables_trends", "Receivables Trends"),
	("erp_analysis.receivables.get_receivables_dashboard", "Receivables Dashboard"),
	("erp_analysis.receivables.get_territory_receivables", "Receivables by Territory"),
	("erp_analysis.receivables.get_customer_statement", "Customer Statement"),
	# Inventory
	("erp_analysis.inventory.get_inventory_snapshot", "Inventory Snapshot"),
	("erp_analysis.inventory.get_inventory_performance", "Inventory Performance"),
	("erp_analysis.inventory.get_inventory_trends", "Inventory Trends"),
	("erp_analysis.inventory.get_inventory_risk", "Inventory Risk"),
	("erp_analysis.inventory.get_inventory_hierarchy", "Inventory Hierarchy"),
	("erp_analysis.inventory.get_inventory_items", "Inventory Items"),
	("erp_analysis.inventory.get_stock_cover", "Stock Cover"),
	("erp_analysis.inventory.get_inventory_health", "Inventory Health"),
	("erp_analysis.inventory.get_dead_stock", "Dead Stock"),
	("erp_analysis.stock.get_inventory_hierarchy", "Inventory Hierarchy (stock alias)"),
	("erp_analysis.stock.get_inventory_items", "Inventory Items (stock alias)"),
	("printechs_utility.inventory.get_inventory_hierarchy", "Inventory Hierarchy (legacy)"),
	("printechs_utility.inventory.get_inventory_snapshot", "Inventory Snapshot (legacy)"),
	("printechs_utility.inventory.get_inventory_items", "Inventory Items (legacy)"),
	# Sales orders
	("erp_analysis.sales_orders.get_order_book_dashboard", "Order Book Dashboard"),
	("erp_analysis.sales_orders.get_sales_order_dashboard", "Sales Order Dashboard (mobile path)"),
	("erp_analysis.sales_orders.get_open_sales_orders", "Open Sales Orders"),
	# Payables / purchase
	("erp_analysis.payables.get_payables_dashboard", "Payables Dashboard"),
	("erp_analysis.payables.get_payment_planning", "Payment Planning"),
	("erp_analysis.purchase.get_purchase_dashboard", "Purchase Dashboard"),
	("erp_analysis.purchase.get_open_purchase_orders", "Open Purchase Orders"),
	# Phase 3 analytics
	("erp_analysis.customer_360.get_customer_360", "Customer 360"),
	("erp_analysis.customer_360.get_customer", "Customer Detail (mobile)"),
	("erp_analysis.profitability.get_gross_profit_dashboard", "Gross Profit Dashboard"),
	("erp_analysis.profitability.get_profitability_dashboard", "Profitability Dashboard (mobile path)"),
	("erp_analysis.exceptions.get_management_exceptions", "Management Exceptions"),
	("erp_analysis.approval_analytics.get_approval_summary", "Approval Analytics"),
	("erp_analysis.approvals.get_approval_analytics", "Approval Analytics (mobile path)"),
	# Approvals
	("erp_analysis.approvals.get_all_approvals", "All Approvals"),
	("erp_analysis.approvals.get_complete_approvals_data", "Complete Approvals Data"),
	("erp_analysis.approvals.approve_document", "Approve Document"),
	("erp_analysis.approvals.reject_document", "Reject Document"),
	("erp_analysis.approvals.sales_invoice", "Sales Invoice Approvals"),
	("erp_analysis.approvals.delivery_note", "Delivery Note Approvals"),
	("erp_analysis.approvals.get_sales_invoice", "Sales Invoice Approval"),
	("erp_analysis.approvals.get_delivery_note", "Delivery Note Approval"),
	("erp_analysis.approvals.get_material_request", "Material Request Approval"),
	("erp_analysis.approvals.get_Payment_Request", "Payment Request Approval"),
	("erp_analysis.approvals.get_stock_entry", "Stock Transfer Approval"),
	# Employee / profile
	("erp_analysis.employee.get_complete_employees_data", "Employees Data"),
	("erp_analysis.employee.get_employee_profile", "Employee Profile"),
	("erp_analysis.employee.get_employees", "Employees List"),
	("erp_analysis.profile.get_complete_profile_data", "Complete Profile"),
	# Catalogue
	("erp_analysis.catalogue.get_catalogues_list", "Catalogues List"),
	("erp_analysis.catalogue.get_catalogue_detail", "Catalogue Detail"),
	("erp_analysis.catalogue.get_catalogue_pages", "Catalogue Pages"),
	("erp_analysis.catalogue.get_catalogue_flip_url", "Catalogue Flip URL"),
	# Notifications
	("erp_analysis.customer_notifications.send_statement_pdf", "Send Statement PDF"),
)

# Registry rows that should grant approve capability on Access Profile lines.
APPROVE_OBJECT_KEYS = frozenset(
	{
		"erp_analysis.approvals.approve_document",
		"erp_analysis.approvals.reject_document",
		"erp_analysis.approvals.sales_invoice",
		"erp_analysis.approvals.delivery_note",
	}
)


def ensure_registry_rows() -> dict[str, str]:
	"""Insert missing Access Object Registry rows. Returns object_key -> registry name."""
	key_to_name: dict[str, str] = {}
	for object_key, label in MOBILE_API_REGISTRY:
		existing = frappe.db.get_value("Access Object Registry", {"object_key": object_key}, "name")
		if existing:
			key_to_name[object_key] = existing
			continue
		doc = frappe.get_doc(
			{
				"doctype": "Access Object Registry",
				"object_type": "API",
				"object_key": object_key,
				"label": label,
				"is_active": 1,
			}
		)
		doc.insert(ignore_permissions=True)
		key_to_name[object_key] = doc.name
	return key_to_name


def sync_access_profiles(key_to_name: dict[str, str]) -> int:
	"""Add missing API lines to every enabled Access Profile. Returns lines added."""
	if not key_to_name:
		return 0

	profiles = frappe.get_all("Access Profile", filters={"enabled": 1}, pluck="name")
	added = 0

	for profile_name in profiles:
		profile = frappe.get_doc("Access Profile", profile_name)
		existing = {row.access_object for row in profile.access_rules if row.access_object}
		changed = False

		for object_key, registry_name in key_to_name.items():
			if registry_name in existing:
				continue
			can_approve = 1 if object_key in APPROVE_OBJECT_KEYS else 0
			profile.append(
				"access_rules",
				{
					"access_object": registry_name,
					"can_view": 1,
					"can_approve": can_approve,
					"active": 1,
				},
			)
			added += 1
			changed = True

		if changed:
			profile.save(ignore_permissions=True)

	return added


def execute():
	if not frappe.db.exists("DocType", "Access Object Registry"):
		return

	key_to_name = ensure_registry_rows()
	added = sync_access_profiles(key_to_name)
	frappe.db.commit()
	clear_caches()

	if added:
		frappe.logger().info(f"sync_mobile_access_registry: added {added} Access Profile line(s)")
