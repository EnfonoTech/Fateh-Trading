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

