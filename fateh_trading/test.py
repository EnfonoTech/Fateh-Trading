import frappe
from frappe.utils import flt, cint

@frappe.whitelist()
def get_item_warehouse_stock(item_code, company=None, limit=8):
    """Return available stock per warehouse for a given item (ERPNext v15-safe)."""
    if not item_code:
        return []

    query = """
        SELECT
            b.warehouse,
            SUM(b.actual_qty) AS actual_qty,
            SUM(b.projected_qty) AS projected_qty
        FROM `tabBin` b
        INNER JOIN `tabWarehouse` w ON b.warehouse = w.name
        WHERE b.item_code = %s
    """
    params = [item_code]

    if company:
        query += " AND w.company = %s"
        params.append(company)

    query += """
        GROUP BY b.warehouse
        ORDER BY SUM(b.projected_qty) DESC
        LIMIT %s
    """
    params.append(cint(limit))

    data = frappe.db.sql(query, tuple(params), as_dict=True)

    for d in data:
        d["actual_qty"] = flt(d.get("actual_qty") or 0)
        d["projected_qty"] = flt(d.get("projected_qty") or 0)

    return data



## Customer Price History



@frappe.whitelist()
def get_item_insights(customer, item_code, company=None, limit=6, other_limit=5):
    """Combined API: customer price history, other customers, stock, stats."""
    if not item_code:
        return {}

    customer = customer or ""

    price_query = """
        SELECT 
            si.name AS si,
            si.posting_date,
            si.customer,
            sid.rate,
            sid.qty,
            sid.stock_qty,
            sid.uom,
            sid.stock_uom,
            sid.conversion_factor,
            si.currency
        FROM `tabSales Invoice Item` sid
        INNER JOIN `tabSales Invoice` si ON sid.parent = si.name
        WHERE sid.item_code = %s
          AND si.docstatus = 1
          AND si.customer = %s
        ORDER BY si.posting_date DESC
        LIMIT %s
    """
    price_history = frappe.db.sql(
        price_query, (item_code, customer, cint(limit)), as_dict=True
    )

    for d in price_history:
        d["rate"] = flt(d.get("rate") or 0)
        d["qty"] = flt(d.get("qty") or 0)
        d["stock_qty"] = flt(d.get("stock_qty") or 0)
        d["conversion_factor"] = flt(d.get("conversion_factor") or 0) or 0
        d["base_rate"] = (
            flt(d["rate"]) / d["conversion_factor"]
            if d["conversion_factor"] and d.get("stock_uom") and d.get("uom")
            and d["stock_uom"] != d["uom"]
            else None
        )

    other_query = """
        SELECT 
            si.name AS si,
            si.posting_date,
            si.customer,
            sid.rate,
            sid.qty,
            sid.stock_qty,
            sid.uom,
            sid.stock_uom,
            sid.conversion_factor,
            si.currency
        FROM `tabSales Invoice Item` sid
        INNER JOIN `tabSales Invoice` si ON sid.parent = si.name
        WHERE sid.item_code = %s
          AND si.docstatus = 1
          AND si.customer != %s
        ORDER BY si.posting_date DESC
        LIMIT %s
    """
    other_customers = frappe.db.sql(
        other_query, (item_code, customer, cint(other_limit)), as_dict=True
    )

    for d in other_customers:
        d["rate"] = flt(d.get("rate") or 0)
        d["qty"] = flt(d.get("qty") or 0)
        d["stock_qty"] = flt(d.get("stock_qty") or 0)
        d["conversion_factor"] = flt(d.get("conversion_factor") or 0) or 0
        d["base_rate"] = (
            flt(d["rate"]) / d["conversion_factor"]
            if d["conversion_factor"] and d.get("stock_uom") and d.get("uom")
            and d["stock_uom"] != d["uom"]
            else None
        )

    stock = get_item_warehouse_stock(item_code=item_code, company=company, limit=8)

    # Last purchase price from Item master
    item_doc = frappe.db.get_value(
        "Item",
        item_code,
        ["last_purchase_rate"],
        as_dict=True,
    )
    last_purchase_rate = flt(item_doc.get("last_purchase_rate") or 0) if item_doc else 0

    # Last rate: stock_uom_rate from last Sales Invoice Item row (same item + customer), fallback to rate
    last_rate = price_history[0]["rate"] if price_history else 0
    try:
        row = frappe.db.sql("""
            SELECT COALESCE(sii.stock_uom_rate, sii.rate) AS last_rate
            FROM `tabSales Invoice Item` sii
            INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
            WHERE sii.item_code = %s AND si.customer = %s AND si.docstatus = 1
            ORDER BY si.posting_date DESC, si.name DESC
            LIMIT 1
        """, (item_code, customer), as_dict=True)
        if row and row[0].get("last_rate") is not None:
            last_rate = flt(row[0]["last_rate"])
    except Exception:
        pass

    return {
        "price_history": price_history,
        "other_customers": other_customers,
        "stock": stock,
        "last_purchase_rate": last_purchase_rate,
        "last_rate": last_rate,
    }


@frappe.whitelist()
def get_item_purchase_insights(supplier, item_code, company=None, limit=6, other_limit=5):
    """Combined API for purchase Price Assist: supplier purchase history, other suppliers, stock, last selling rate."""
    if not item_code:
        return {}

    supplier = supplier or ""

    # Purchase history from both Purchase Invoice and Purchase Receipt for this supplier
    pi_query = """
        SELECT
            pi.name AS doc_name,
            'Purchase Invoice' AS doctype,
            pi.posting_date,
            pi.supplier,
            pii.rate,
            pii.qty,
            pii.stock_qty,
            pii.uom,
            pii.stock_uom,
            pii.conversion_factor,
            pi.currency
        FROM `tabPurchase Invoice Item` pii
        INNER JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent
        WHERE pii.item_code = %s AND pi.docstatus = 1 AND pi.supplier = %s
        ORDER BY pi.posting_date DESC
        LIMIT %s
    """
    pr_query = """
        SELECT
            pr.name AS doc_name,
            'Purchase Receipt' AS doctype,
            pr.posting_date,
            pr.supplier,
            pri.rate,
            pri.qty,
            pri.stock_qty,
            pri.uom,
            pri.stock_uom,
            pri.conversion_factor,
            pr.currency
        FROM `tabPurchase Receipt Item` pri
        INNER JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
        WHERE pri.item_code = %s AND pr.docstatus = 1 AND pr.supplier = %s
        ORDER BY pr.posting_date DESC
        LIMIT %s
    """
    lim = cint(limit)
    pi_rows = frappe.db.sql(pi_query, (item_code, supplier, lim), as_dict=True)
    pr_rows = frappe.db.sql(pr_query, (item_code, supplier, lim), as_dict=True)
    # Merge and sort by posting_date desc, take up to limit
    price_history = []
    for d in pi_rows:
        d["rate"] = flt(d.get("rate") or 0)
        d["si"] = d["doc_name"]  # reuse key for UI
        price_history.append(d)
    for d in pr_rows:
        d["rate"] = flt(d.get("rate") or 0)
        d["si"] = d["doc_name"]
        price_history.append(d)
    price_history.sort(key=lambda x: (x.get("posting_date") or "", x.get("doc_name") or ""), reverse=True)
    price_history = price_history[:lim]

    # Other suppliers (from PI and PR)
    other_pi = frappe.db.sql("""
        SELECT pi.name AS doc_name, 'Purchase Invoice' AS doctype, pi.posting_date, pi.supplier,
               pii.rate, pii.qty, pii.stock_qty, pii.uom, pii.stock_uom, pii.conversion_factor, pi.currency
        FROM `tabPurchase Invoice Item` pii
        INNER JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent
        WHERE pii.item_code = %s AND pi.docstatus = 1 AND pi.supplier != %s
        ORDER BY pi.posting_date DESC
        LIMIT %s
    """, (item_code, supplier, cint(other_limit)), as_dict=True)
    other_pr = frappe.db.sql("""
        SELECT pr.name AS doc_name, 'Purchase Receipt' AS doctype, pr.posting_date, pr.supplier,
               pri.rate, pri.qty, pri.stock_qty, pri.uom, pri.stock_uom, pri.conversion_factor, pr.currency
        FROM `tabPurchase Receipt Item` pri
        INNER JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
        WHERE pri.item_code = %s AND pr.docstatus = 1 AND pr.supplier != %s
        ORDER BY pr.posting_date DESC
        LIMIT %s
    """, (item_code, supplier, cint(other_limit)), as_dict=True)
    other_suppliers = list(other_pi) + list(other_pr)
    for d in other_suppliers:
        d["rate"] = flt(d.get("rate") or 0)
        d["customer"] = d.get("supplier")  # UI expects "customer" key for other-party label
    other_suppliers.sort(key=lambda x: (x.get("posting_date") or "", x.get("doc_name") or ""), reverse=True)
    other_suppliers = other_suppliers[: cint(other_limit)]

    stock = get_item_warehouse_stock(item_code=item_code, company=company, limit=8)

    # Last purchase rate for this supplier (from PI/PR)
    last_rate = 0
    if price_history:
        last_rate = flt(price_history[0].get("rate") or 0)
    else:
        row = frappe.db.sql("""
            SELECT COALESCE(pii.stock_uom_rate, pii.rate) AS last_rate
            FROM `tabPurchase Invoice Item` pii
            INNER JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent
            WHERE pii.item_code = %s AND pi.supplier = %s AND pi.docstatus = 1
            ORDER BY pi.posting_date DESC, pi.name DESC
            LIMIT 1
        """, (item_code, supplier), as_dict=True)
        if row and row[0].get("last_rate") is not None:
            last_rate = flt(row[0]["last_rate"])
        else:
            row = frappe.db.sql("""
                SELECT COALESCE(pri.stock_uom_rate, pri.rate) AS last_rate
                FROM `tabPurchase Receipt Item` pri
                INNER JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
                WHERE pri.item_code = %s AND pr.supplier = %s AND pr.docstatus = 1
                ORDER BY pr.posting_date DESC, pr.name DESC
                LIMIT 1
            """, (item_code, supplier), as_dict=True)
            if row and row[0].get("last_rate") is not None:
                last_rate = flt(row[0]["last_rate"])

    # Last purchase rate from Item master; valuation rate from Bin (stock), not Item master
    item_doc = frappe.db.get_value("Item", item_code, "last_purchase_rate", as_dict=True)
    last_purchase_rate = flt(item_doc.get("last_purchase_rate") or 0) if item_doc else 0

    valuation_rate = 0
    bin_query = """
        SELECT SUM(b.stock_value) / NULLIF(SUM(b.actual_qty), 0) AS valuation_rate
        FROM `tabBin` b
        WHERE b.item_code = %s AND b.actual_qty > 0
    """
    bin_params = [item_code]
    if company:
        bin_query += " AND EXISTS (SELECT 1 FROM `tabWarehouse` w WHERE w.name = b.warehouse AND w.company = %s)"
        bin_params.append(company)
    row = frappe.db.sql(bin_query, tuple(bin_params), as_dict=True)
    if row and row[0].get("valuation_rate") is not None:
        valuation_rate = flt(row[0]["valuation_rate"])

    return {
        "price_history": price_history,
        "other_customers": other_suppliers,
        "stock": stock,
        "last_purchase_rate": last_purchase_rate,
        "last_rate": last_rate,
        "valuation_rate": valuation_rate,
    }

