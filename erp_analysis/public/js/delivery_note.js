// Always keep Set Source Warehouse filled (Strict UP list visibility).
frappe.ui.form.on("Delivery Note", {
	onload(frm) {
		erp_analysis_dn_ensure_set_warehouse(frm);
	},
	refresh(frm) {
		erp_analysis_dn_ensure_set_warehouse(frm);
	},
	user_default_warehouse(frm) {
		if (!frm.doc.set_warehouse && frm.doc.user_default_warehouse) {
			frm.set_value("set_warehouse", frm.doc.user_default_warehouse);
		}
	},
	items_add(frm) {
		erp_analysis_dn_ensure_set_warehouse(frm);
	},
});

frappe.ui.form.on("Delivery Note Item", {
	warehouse(frm) {
		erp_analysis_dn_ensure_set_warehouse(frm);
	},
});

function erp_analysis_dn_ensure_set_warehouse(frm) {
	if (frm.doc.set_warehouse) {
		return;
	}
	let warehouse = frm.doc.user_default_warehouse;
	if (!warehouse && frm.doc.items && frm.doc.items.length) {
		const row = frm.doc.items.find((r) => r.warehouse);
		warehouse = row && row.warehouse;
	}
	if (!warehouse && frappe.boot.user && frappe.boot.user.defaults) {
		warehouse = frappe.boot.user.defaults.warehouse || frappe.boot.user.defaults.default_warehouse;
	}
	if (warehouse) {
		frm.set_value("set_warehouse", warehouse);
	}
}
