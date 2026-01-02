import frappe

@frappe.whitelist()
def get_item_sales_history(item_code=None, limit=20):
    """Get item sales history with last purchase rates"""
    # permission check
    if not frappe.has_permission("Sales Invoice", "read"):
        frappe.throw("Not permitted", frappe.PermissionError)

    limit = int(limit or 20)
    where = ["si.docstatus = 1"]
    params = {"limit": limit}

    if item_code:
        where.append("sii.item_code = %(item_code)s")
        params["item_code"] = item_code

    where_sql = " AND ".join(where)

    rows = frappe.db.sql(f"""
        SELECT
            si.posting_date,
            si.name           AS sales_invoice,
            si.customer,
            si.company,
            sii.item_code,
            sii.item_name,
            sii.qty,
            sii.uom,
            sii.rate          AS sales_rate,
            sii.amount        AS sales_amount,
            si.currency,
            (
                SELECT pii.rate
                FROM `tabPurchase Invoice Item` pii
                JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent
                WHERE pi.docstatus = 1
                  AND pii.item_code = sii.item_code
                ORDER BY pi.posting_date DESC, pi.name DESC
                LIMIT 1
            ) AS last_purchase_rate
        FROM `tabSales Invoice Item` sii
        JOIN `tabSales Invoice` si ON si.name = sii.parent
        WHERE {where_sql}
        ORDER BY si.posting_date DESC, si.name DESC, sii.idx ASC
        LIMIT %(limit)s
    """, params, as_dict=True)

    return rows

