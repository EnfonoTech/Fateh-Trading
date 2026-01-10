frappe.ui.form.on("Purchase Invoice", {
    custom_weighted_discount(frm) {
        apply_weighted_discount(frm);
    }
});

frappe.ui.form.on("Purchase Invoice Item", {
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
    },

    custom_discount_on_amount(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        
        if (row.custom_discount_on_amount) {
            const discount_per_unit = row.custom_discount_on_amount / row.qty;
            const new_rate = row.rate - discount_per_unit;
            frappe.model.set_value(cdt, cdn, "rate", new_rate);
        }
    }
});
