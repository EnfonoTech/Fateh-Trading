import frappe
from frappe.utils import flt

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
def get_price_history(item_code=None, customer=None):

    if not item_code:
        frappe.throw("item_code is required")

    # =========================
    # CUSTOMER DETAILS
    # =========================
    customer_name = None
    header_customer = None

    if customer:
        customer_name = frappe.db.get_value("Customer", customer, "customer_name")
        header_customer = f"{customer_name} · {customer}"

    # =========================
    # MSP RATES (ITEM LEVEL)
    # =========================
    traders_msp = frappe.db.get_value("Item Price", {
        "item_code": item_code,
        "price_list": "Traders MSP"
    }, "price_list_rate")

    retail_msp = frappe.db.get_value("Item Price", {
        "item_code": item_code,
        "price_list": "Retail MSP"
    }, "price_list_rate")

    # =========================
    # RECENT INVOICES
    # =========================
    recent_invoices = frappe.db.sql("""
        SELECT 
            sii.parent as invoice,
            si.customer,
            sii.rate,
            si.posting_date
        FROM `tabSales Invoice Item` sii
        INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
        WHERE sii.item_code = %s
        ORDER BY si.posting_date DESC
        LIMIT 10
    """, item_code, as_dict=1)

    # Replace customer ID → name
    for r in recent_invoices:
        r.customer_name = frappe.db.get_value(
            "Customer",
            r.customer,
            "customer_name"
        )

    # =========================
    # RESPONSE
    # =========================
    return {
        "header": {
            "customer_id": customer,
            "customer_name": customer_name,
            "display": header_customer
        },
        "item_code": item_code,
        "stats": {
            "traders_msp": traders_msp,
            "retail_msp": retail_msp
        },
        "recent_invoices": recent_invoices
    }


@frappe.whitelist()
def get_item_purchase_history(item_code=None, supplier=None, limit=20):
    """Get item purchase history popup data - Purchase Invoice item row"""
    if not frappe.has_permission("Purchase Invoice", "read"):
        frappe.throw("Not permitted", frappe.PermissionError)
 
    # FIX 4: safe int conversion
    try:
        limit = int(limit or 20)
    except (ValueError, TypeError):
        limit = 20
 
    # ------------------------------------------------------------------
    # 1. Purchase invoice history rows
    # ------------------------------------------------------------------
    where = ["pi.docstatus = 1"]
    params = {"limit": limit}
 
    if item_code:
        where.append("pii.item_code = %(item_code)s")
        params["item_code"] = item_code
 
    if supplier:
        where.append("pi.supplier = %(supplier)s")
        params["supplier"] = supplier
 
    where_sql = " AND ".join(where)
 
    # FIX 2: removed pii.stock_uom_rate — not present on all ERPNext versions
    history = frappe.db.sql(f"""
        SELECT
            pi.posting_date,
            pi.name               AS purchase_invoice,
            pi.supplier,
            sup.supplier_name,
            pi.company,
            pii.item_code,
            pii.item_name,
            pii.qty,
            pii.stock_qty,
            pii.uom,
            pii.rate              AS purchase_rate,
            pii.amount            AS purchase_amount,
            pi.currency,
            item.last_purchase_rate
        FROM `tabPurchase Invoice Item` pii
        JOIN `tabPurchase Invoice` pi  ON pi.name  = pii.parent
        LEFT JOIN `tabSupplier`   sup  ON sup.name = pi.supplier
        LEFT JOIN `tabItem`       item ON item.name = pii.item_code
        WHERE {where_sql}
        ORDER BY pi.posting_date DESC, pi.name DESC, pii.idx ASC
        LIMIT %(limit)s
    """, params, as_dict=True)
 
    # ------------------------------------------------------------------
    # 2. Stat cards — Last (this supplier), Valuation Rate, Current Rate
    # ------------------------------------------------------------------
    stat_cards = {
        "last_supplier_rate": None,
        "last_supplier_name": None,
        "last_supplier_id":   None,
        "valuation_rate":     None,
        "current_rate":       None,
        "currency":           None,
        "stock_uom":          None,
    }
 
    if item_code:
        sc_where = "pi.docstatus = 1 AND pii.item_code = %(item_code)s"
        sc_params = {"item_code": item_code}
        if supplier:
            sc_where += " AND pi.supplier = %(supplier)s"
            sc_params["supplier"] = supplier
 
        last_row = frappe.db.sql(f"""
            SELECT
                pii.rate        AS last_rate,
                pi.supplier,
                sup.supplier_name,
                pi.currency
            FROM `tabPurchase Invoice Item` pii
            JOIN `tabPurchase Invoice` pi  ON pi.name  = pii.parent
            LEFT JOIN `tabSupplier`   sup  ON sup.name = pi.supplier
            WHERE {sc_where}
            ORDER BY pi.posting_date DESC, pi.name DESC
            LIMIT 1
        """, sc_params, as_dict=True)
 
        if last_row:
            stat_cards["last_supplier_rate"] = last_row[0].last_rate
            stat_cards["last_supplier_name"] = last_row[0].supplier_name or last_row[0].supplier
            stat_cards["last_supplier_id"]   = last_row[0].supplier
            stat_cards["currency"]           = last_row[0].currency
 
        # FIX 5: get valuation_rate from tabBin (reliable) not Item master
        # weighted average across all warehouses: sum(stock_value) / sum(actual_qty)
        val_row = frappe.db.sql("""
            SELECT
                SUM(b.stock_value) / NULLIF(SUM(b.actual_qty), 0) AS valuation_rate,
                i.stock_uom
            FROM `tabBin` b
            JOIN `tabItem` i ON i.name = b.item_code
            WHERE b.item_code = %(item_code)s
              AND b.actual_qty > 0
            GROUP BY b.item_code
        """, {"item_code": item_code}, as_dict=True)
 
        if val_row:
            stat_cards["valuation_rate"] = flt(val_row[0].valuation_rate)
            stat_cards["stock_uom"]      = val_row[0].stock_uom
 
        # current_rate = last_purchase_rate from Item master (still reliable for this)
        last_purchase_rate = frappe.db.get_value("Item", item_code, "last_purchase_rate")
        stat_cards["current_rate"] = flt(last_purchase_rate)
 
        # stock_uom fallback if no bin rows
        if not stat_cards["stock_uom"]:
            stat_cards["stock_uom"] = frappe.db.get_value("Item", item_code, "stock_uom")
 
    # ------------------------------------------------------------------
    # 3. Other suppliers — last rate per supplier, name as primary
    # FIX 1: use ORDER BY + LIMIT subquery instead of correlated MAX()
    #         so the rate returned always matches the latest invoice
    # ------------------------------------------------------------------
    other_suppliers = []
 
    if item_code:
        os_where = "pi.docstatus = 1 AND pii.item_code = %(item_code)s"
        os_params = {"item_code": item_code}
        if supplier:
            os_where += " AND pi.supplier != %(exclude_supplier)s"
            os_params["exclude_supplier"] = supplier
 
        other_suppliers = frappe.db.sql(f"""
            SELECT
                pi.supplier,
                sup.supplier_name,
                pi.currency,
                pi.posting_date  AS last_date,
                pii.rate         AS last_rate,
                pi.name          AS purchase_invoice
            FROM `tabPurchase Invoice Item` pii
            JOIN `tabPurchase Invoice` pi  ON pi.name  = pii.parent
            LEFT JOIN `tabSupplier`   sup  ON sup.name = pi.supplier
            WHERE {os_where}
              AND pi.name = (
                    SELECT pi2.name
                    FROM `tabPurchase Invoice` pi2
                    JOIN `tabPurchase Invoice Item` pii2
                        ON pii2.parent = pi2.name
                    WHERE pi2.docstatus    = 1
                      AND pii2.item_code  = pii.item_code
                      AND pi2.supplier    = pi.supplier
                    ORDER BY pi2.posting_date DESC, pi2.name DESC
                    LIMIT 1
              )
            GROUP BY pi.supplier
            ORDER BY last_date DESC
            LIMIT 20
        """, os_params, as_dict=True)
 
        for row in other_suppliers:
            if not row.get("supplier_name"):
                row["supplier_name"] = row["supplier"]
 
    # ------------------------------------------------------------------
    # 4. Stock by warehouse
    # FIX 3: query tabBin directly — it's always current, fast, and correct
    # ------------------------------------------------------------------
    stock_by_warehouse = []
 
    if item_code:
        stock_by_warehouse = frappe.db.sql("""
            SELECT
                b.warehouse,
                b.actual_qty,
                i.stock_uom
            FROM `tabBin` b
            JOIN `tabItem` i ON i.name = b.item_code
            WHERE b.item_code  = %(item_code)s
              AND b.actual_qty > 0
            ORDER BY b.actual_qty DESC
        """, {"item_code": item_code}, as_dict=True)
 
    return {
        "history"            : history,
        "stat_cards"         : stat_cards,
        "other_suppliers"    : other_suppliers,
        "stock_by_warehouse" : stock_by_warehouse,
    }
 

def update_customer_item_price(doc, method):

    if not doc.customer or doc.docstatus != 1:
        return

    price_list = "Standard Selling"

    for item in doc.items:
        if not item.rate or item.rate <= 0:
            continue

        stock_uom = frappe.db.get_value("Item", item.item_code, "stock_uom")
        conversion_factor = item.conversion_factor or 1

        if item.uom != stock_uom:
            rate_per_stock_uom = item.rate / conversion_factor
        else:
            rate_per_stock_uom = item.rate

        existing = frappe.db.get_value(
            "Item Price",
            {
                "item_code": item.item_code,
                "price_list": price_list,
                "customer": doc.customer
            },
            "name"
        )

        if existing:
            ip = frappe.get_doc("Item Price", existing)

            if ip.price_list_rate != rate_per_stock_uom:
                ip.price_list_rate = rate_per_stock_uom
                ip.save(ignore_permissions=True)

        else:
            ip = frappe.new_doc("Item Price")
            ip.item_code = item.item_code
            ip.price_list = price_list
            ip.price_list_rate = rate_per_stock_uom
            ip.customer = doc.customer
            ip.selling = 1
            ip.currency = doc.currency
            ip.insert(ignore_permissions=True)