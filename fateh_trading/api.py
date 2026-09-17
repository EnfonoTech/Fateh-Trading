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
            cust.customer_name,
            si.company,
            sii.item_code,
            sii.item_name,
            sii.qty,
            sii.stock_qty,
            sii.uom,
            sii.rate          AS sales_rate,
            sii.amount        AS sales_amount,
            si.currency,
            item.last_purchase_rate,
            sii.stock_uom_rate
        FROM `tabSales Invoice Item` sii
        JOIN `tabSales Invoice` si ON si.name = sii.parent
        LEFT JOIN `tabCustomer` cust ON cust.name = si.customer
        LEFT JOIN `tabItem` item ON item.name = sii.item_code
        WHERE {where_sql}
        ORDER BY si.posting_date DESC, si.name DESC, sii.idx ASC
        LIMIT %(limit)s
    """, params, as_dict=True)

    return rows


_PURCHASE_SOURCES = (
    ("Purchase Invoice", "Purchase Invoice Item", "pi", "pii"),
    ("Purchase Receipt", "Purchase Receipt Item", "pr", "pri"),
)


def _last_selling_rates(item_codes):
    """item_code -> stock-UOM rate from that item's most recent Sales Invoice."""
    item_codes = list({code for code in (item_codes or []) if code})
    if not item_codes:
        return {}

    placeholders = ", ".join(["%s"] * len(item_codes))
    rows = frappe.db.sql(
        f"""
        SELECT item_code, last_selling_rate FROM (
            SELECT
                sii.item_code,
                COALESCE(sii.stock_uom_rate, sii.rate) AS last_selling_rate,
                ROW_NUMBER() OVER (
                    PARTITION BY sii.item_code
                    ORDER BY si.posting_date DESC, si.name DESC
                ) AS rn
            FROM `tabSales Invoice Item` sii
            INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
            WHERE si.docstatus = 1 AND sii.item_code IN ({placeholders})
        ) ranked WHERE rn = 1
        """,
        tuple(item_codes),
        as_dict=True,
    )
    return {row["item_code"]: row["last_selling_rate"] for row in rows}


@frappe.whitelist()
def get_item_purchase_history(item_code=None, limit=20):
    """Get item purchase history across Purchase Invoice and Purchase Receipt"""
    if not frappe.has_permission("Purchase Invoice", "read"):
        frappe.throw("Not permitted", frappe.PermissionError)

    limit = int(limit or 20)
    params = {"limit": limit, "item_code": item_code}

    blocks = []
    for parent, child, p, c in _PURCHASE_SOURCES:
        where = f"{p}.docstatus = 1"
        if item_code:
            where += f" AND {c}.item_code = %(item_code)s"
        blocks.append(f"""
            (SELECT
                {p}.posting_date,
                {p}.name AS doc_name,
                '{parent}' AS doctype,
                {p}.supplier,
                sup.supplier_name,
                {p}.company,
                {c}.item_code,
                {c}.item_name,
                {c}.qty,
                {c}.stock_qty,
                {c}.rate AS purchase_rate,
                {c}.amount,
                {p}.currency,
                {c}.stock_uom_rate
            FROM `tab{child}` {c}
            JOIN `tab{parent}` {p} ON {p}.name = {c}.parent
            LEFT JOIN `tabSupplier` sup ON sup.name = {p}.supplier
            WHERE {where})
        """)

    rows = frappe.db.sql(
        " UNION ALL ".join(blocks) + " ORDER BY posting_date DESC, doc_name DESC LIMIT %(limit)s",
        params,
        as_dict=True,
    )

    last_selling = _last_selling_rates([row.get("item_code") for row in rows])
    for row in rows:
        row["last_selling_rate"] = last_selling.get(row.get("item_code")) or 0

    return rows
