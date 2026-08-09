// Filter Mode of Payment by Payment Entry warehouse:
// blank warehouse (Wire Transfer*) always allowed; city MoPs match user_default_warehouse.
frappe.ui.form.on("Payment Entry", {
	setup(frm) {
		frm.set_query("mode_of_payment", () => {
			const warehouse = frm.doc.user_default_warehouse;
			if (!warehouse) {
				return { filters: { enabled: 1 } };
			}
			return {
				query: "erp_analysis.permissions.mode_of_payment.payment_entry_mop_query",
				filters: { warehouse },
			};
		});
	},
});
