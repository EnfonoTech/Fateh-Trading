frappe.ui.form.on("Quotation", {
    custom_weighted_discount(frm) {
        apply_weighted_discount(frm);
    }
});

frappe.ui.form.on("Quotation Item", {
    rate(frm, cdt, cdn) {
        const row = locals[cdt][cdn];

        if (!row.custom_actual_rate) {
            frappe.model.set_value(cdt, cdn, "custom_actual_rate", row.rate);
        }
    },

    item_code(frm, cdt, cdn) {
        const row = locals[cdt][cdn];

        if (!row.custom_actual_rate && row.rate) {
            frappe.model.set_value(cdt, cdn, "custom_actual_rate", row.rate);
        }
    }
});
