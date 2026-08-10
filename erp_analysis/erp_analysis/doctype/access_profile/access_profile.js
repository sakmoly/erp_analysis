// Copyright (c) 2025, Printechs and contributors
// For license information, please see license.txt

frappe.ui.form.on("Access Profile", {
	onload(frm) {
		frm.set_query("access_object", "access_rules", () => ({
			query: "erp_analysis.erp_analysis.doctype.access_profile.access_profile.access_object_link_query",
			filters: { is_active: 1 },
		}));

		if (frm.is_new() && !(frm.doc.access_rules || []).length) {
			load_default_access_rules(frm);
		}
	},

	refresh(frm) {
		frm.set_query("access_object", "access_rules", () => ({
			query: "erp_analysis.erp_analysis.doctype.access_profile.access_profile.access_object_link_query",
			filters: { is_active: 1 },
		}));

		frm.add_custom_button(__("Load All Access Objects"), () => {
			frappe.confirm(
				__(
					"Add any missing Access Object Registry items to Access Rules? Existing rows are kept."
				),
				() => load_default_access_rules(frm, { merge: true })
			);
		}, __("Access Rules"));

		frm.add_custom_button(__("Select All Can View"), () => {
			set_access_flag(frm, "can_view", 1);
		}, __("Access Rules"));

		frm.add_custom_button(__("Clear Can View"), () => {
			set_access_flag(frm, "can_view", 0);
		}, __("Access Rules"));

		frm.add_custom_button(__("Select All Can Approve"), () => {
			set_access_flag(frm, "can_approve", 1);
		}, __("Access Rules"));

		frm.add_custom_button(__("Clear Can Approve"), () => {
			set_access_flag(frm, "can_approve", 0);
		}, __("Access Rules"));
	},
});

function set_access_flag(frm, fieldname, value) {
	(frm.doc.access_rules || []).forEach((row) => {
		frappe.model.set_value(row.doctype, row.name, fieldname, value);
	});
	frm.refresh_field("access_rules");
	frm.dirty();
}

function load_default_access_rules(frm, opts) {
	opts = opts || {};
	frappe.call({
		method: "erp_analysis.erp_analysis.doctype.access_profile.access_profile.get_default_access_rules",
		freeze: true,
		freeze_message: __("Loading Access Objects..."),
		callback(r) {
			const rows = r.message || [];
			if (!rows.length) {
				frappe.msgprint(__("No active Access Object Registry entries found."));
				return;
			}

			if (!opts.merge) {
				frm.clear_table("access_rules");
			}

			const existing = new Set(
				(frm.doc.access_rules || []).map((row) => row.access_object).filter(Boolean)
			);
			let added = 0;
			rows.forEach((row) => {
				if (existing.has(row.access_object)) {
					return;
				}
				frm.add_child("access_rules", row);
				added += 1;
			});
			frm.refresh_field("access_rules");
			frm.dirty();
			frappe.show_alert({
				message: __("Access Rules ready ({0} objects, {1} added)", [
					rows.length,
					added,
				]),
				indicator: "green",
			});
		},
	});
}
