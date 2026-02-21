import frappe


def _get_last_selling_rates(item_codes):
    """Return dict item_code -> last_selling_rate from latest Sales Invoice."""
    if not item_codes:
        return {}
    item_codes = list(set(item_codes))
    placeholders = ", ".join(["%s"] * len(item_codes))
    try:
        rows = frappe.db.sql("""
            SELECT item_code, last_selling_rate FROM (
                SELECT sii.item_code,
                    COALESCE(sii.stock_uom_rate, sii.rate) AS last_selling_rate,
                    ROW_NUMBER() OVER (PARTITION BY sii.item_code ORDER BY si.posting_date DESC, si.name DESC) AS rn
                FROM `tabSales Invoice Item` sii
                INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
                WHERE si.docstatus = 1 AND sii.item_code IN ({0})
            ) t WHERE rn = 1
        """.format(placeholders), tuple(item_codes), as_dict=True)
        return {r["item_code"]: r["last_selling_rate"] for r in rows}
    except Exception:
        # Fallback for DB without ROW_NUMBER (e.g. MySQL 5.7)
        result = {}
        for code in item_codes:
            row = frappe.db.sql("""
                SELECT COALESCE(sii.stock_uom_rate, sii.rate) AS last_selling_rate
                FROM `tabSales Invoice Item` sii
                INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
                WHERE si.docstatus = 1 AND sii.item_code = %s
                ORDER BY si.posting_date DESC, si.name DESC
                LIMIT 1
            """, (code,), as_dict=True)
            if row:
                result[code] = row[0].get("last_selling_rate") or 0
        return result


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


@frappe.whitelist()
def get_item_purchase_history(item_code=None, limit=20):
    """Get item purchase history from Purchase Invoice and Purchase Receipt."""
    if not frappe.has_permission("Purchase Invoice", "read"):
        frappe.throw("Not permitted", frappe.PermissionError)

    limit = int(limit or 20)
    params = {"limit": limit, "item_code": item_code}

    # Purchase Invoice Items
    where_pi = "pi.docstatus = 1"
    if item_code:
        where_pi += " AND pii.item_code = %(item_code)s"

    # Purchase Receipt Items (union with PI for combined history)
    where_pr = "pr.docstatus = 1"
    if item_code:
        where_pr += " AND pri.item_code = %(item_code)s"

    sql = f"""
        (SELECT
            pi.posting_date,
            pi.name AS doc_name,
            'Purchase Invoice' AS doctype,
            pi.supplier,
            sup.supplier_name,
            pi.company,
            pii.item_code,
            pii.item_name,
            pii.qty,
            pii.stock_qty,
            pii.rate AS purchase_rate,
            pii.amount,
            pi.currency,
            pii.stock_uom_rate
        FROM `tabPurchase Invoice Item` pii
        JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent
        LEFT JOIN `tabSupplier` sup ON sup.name = pi.supplier
        WHERE {where_pi})
        UNION ALL
        (SELECT
            pr.posting_date,
            pr.name AS doc_name,
            'Purchase Receipt' AS doctype,
            pr.supplier,
            sup.supplier_name,
            pr.company,
            pri.item_code,
            pri.item_name,
            pri.qty,
            pri.stock_qty,
            pri.rate AS purchase_rate,
            pri.amount,
            pr.currency,
            pri.stock_uom_rate
        FROM `tabPurchase Receipt Item` pri
        JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
        LEFT JOIN `tabSupplier` sup ON sup.name = pr.supplier
        WHERE {where_pr})
        ORDER BY posting_date DESC, doc_name DESC
        LIMIT %(limit)s
    """
    rows = frappe.db.sql(sql, params, as_dict=True)

    item_codes = list({r["item_code"] for r in rows if r.get("item_code")})
    last_selling = _get_last_selling_rates(item_codes)
    for r in rows:
        r["last_selling_rate"] = last_selling.get(r.get("item_code")) or 0

    return rows

