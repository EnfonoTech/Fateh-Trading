frappe.ui.form.on("Sales Invoice", {
    custom_weighted_discount(frm) {
        apply_weighted_discount(frm);
    }
});

frappe.ui.form.on("Sales Invoice Item", {
    rate(frm, cdt, cdn) {
        const row = locals[cdt][cdn];

        // Skip if this is a programmatic change
        if (row.__updating_rate_programmatically) {
            return;
        }

        frappe.model.set_value(cdt, cdn, "custom_discount_on_amount", null);
        
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
            
            // Set flag before programmatic update
            row.__updating_rate_programmatically = true;
            
            frappe.model.set_value(cdt, cdn, "rate", new_rate);
            
            // Clean up flag after a short delay to ensure the rate event has processed
            setTimeout(() => {
                delete row.__updating_rate_programmatically;
            }, 100);
        }
    }
});
