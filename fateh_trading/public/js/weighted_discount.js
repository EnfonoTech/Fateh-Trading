window.apply_weighted_discount = function (frm) {
    const discount = flt(frm.doc.custom_weighted_discount || 0);
    if (!discount || !frm.doc.items || frm.doc.items.length === 0) return;

    let total_actual_rate = 0;

    frm.doc.items.forEach(row => {
        total_actual_rate += flt(row.custom_actual_rate || row.rate || 0);
    });

    if (!total_actual_rate) return;

    frm.doc.items.forEach(row => {
        const actual_rate = flt(row.custom_actual_rate || row.rate || 0);
        const ratio = actual_rate / total_actual_rate;

        const item_discount = flt(discount * ratio);
        const new_rate = flt(actual_rate - item_discount);

        frappe.model.set_value(row.doctype, row.name, "custom_item_discount", item_discount);
        frappe.model.set_value(row.doctype, row.name, "rate", new_rate);
    });

    frm.refresh_field("items");
};
