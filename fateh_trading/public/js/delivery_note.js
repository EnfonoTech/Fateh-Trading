frappe.ui.form.on("Delivery Note Item", {

    custom_discount_on_amount(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        
        if (row.custom_discount_on_amount) {
            const discount_per_unit = row.custom_discount_on_amount / row.qty;
            const new_rate = row.rate - discount_per_unit;
            frappe.model.set_value(cdt, cdn, "rate", new_rate);
        }
    }
});
