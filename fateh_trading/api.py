
import frappe

@frappe.whitelist()
def get_item_sales_history(item_code=None, limit=20):
    """Get item sales history, hide last_purchase_rate if purchase permissions missing"""
 
      # Sales Invoice read must
    if not frappe.has_permission("Sales Invoice", "read"):
        frappe.throw("Not permitted", frappe.PermissionError)

    user = frappe.session.user
    limit = int(limit or 20)

    where = ["si.docstatus = 1"]
    params = {
        "limit": limit,
        "user": user
    }
   
    if item_code:
        where.append("sii.item_code = %(item_code)s")
        params["item_code"] = item_code

      # Customer User Permission logic
    
    where.append("""
        (
            NOT EXISTS (
                SELECT 1
                FROM `tabUser Permission` up
                WHERE up.user = %(user)s
                  AND up.allow = 'Customer'
            )
            OR EXISTS (
                SELECT 1
                FROM `tabUser Permission` up
                WHERE up.user = %(user)s
                  AND up.allow = 'Customer'
                  AND up.for_value = si.customer
            )
        )
    """)

    where_sql = " AND ".join(where)

    rows = frappe.db.sql(f"""
        SELECT
            si.posting_date,
            si.customer_name AS sales_invoice,
            si.customer,
            si.company,
            sii.item_code,
            sii.item_name,
            sii.qty,
            sii.uom,
            sii.rate   AS sales_rate,
            sii.amount AS sales_amount,
            si.currency,
            it.last_purchase_rate
        FROM `tabSales Invoice Item` sii
        JOIN `tabSales Invoice` si
            ON si.name = sii.parent
        LEFT JOIN `tabItem` it
            ON it.name = sii.item_code
        WHERE {where_sql}
        ORDER BY si.posting_date DESC, si.name DESC, sii.idx ASC           
        LIMIT %(limit)s
    """, params, as_dict=True)

      # Hide last purchase rate if no purchase permission
    if not (
        frappe.has_permission("Purchase Invoice", "read")
        and frappe.has_permission("Purchase Receipt", "read")
    ):
        for row in rows:
            row.pop("last_purchase_rate", None)

    return rows
