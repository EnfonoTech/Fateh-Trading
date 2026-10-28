import erpnext
import frappe
from frappe.utils import cint, flt


def _add_arabic_names(rows, *, party_doctype, party_key, arabic_party_field):
    """Attach Arabic item / party names to history rows.

    Two bulk lookups (items, parties) instead of a join, and skipped quietly on
    a site where the Arabic custom fields do not exist.
    """
    if not rows:
        return

    def _arabic_map(doctype, field, names):
        names = [n for n in set(names) if n]
        if not names or not frappe.get_meta(doctype).has_field(field):
            return {}
        return {
            d.name: d.get(field)
            for d in frappe.get_all(
                doctype, filters={"name": ["in", names]}, fields=["name", field]
            )
        }

    item_ar = _arabic_map("Item", "custom_item_name_arabic", [r.get("item_code") for r in rows])
    party_ar = _arabic_map(party_doctype, arabic_party_field, [r.get(party_key) for r in rows])
    for r in rows:
        r["item_name_arabic"] = item_ar.get(r.get("item_code")) or ""
        r["party_name_arabic"] = party_ar.get(r.get(party_key)) or ""


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
                    COALESCE(sii.stock_uom_rate, sii.rate) * IFNULL(NULLIF(si.conversion_rate, 0), 1) AS last_selling_rate,
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
                SELECT COALESCE(sii.stock_uom_rate, sii.rate) * IFNULL(NULLIF(si.conversion_rate, 0), 1) AS last_selling_rate
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

    params = {"limit": min(cint(limit) or 20, 200), "item_code": item_code or ""}

    rows = frappe.db.sql("""
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
        WHERE si.docstatus = 1
          AND (%(item_code)s = '' OR sii.item_code = %(item_code)s)
        ORDER BY si.posting_date DESC, si.name DESC, sii.idx ASC
        LIMIT %(limit)s
    """, params, as_dict=True)

    _add_arabic_names(
        rows,
        party_doctype="Customer",
        party_key="customer",
        arabic_party_field="custom_customer_name_arabic",
    )
    return rows


@frappe.whitelist()
def get_item_purchase_history(item_code=None, limit=20):
    """Get item purchase history from Purchase Invoice and Purchase Receipt.

    Rates are returned per stock UOM, *net* of discounts: `net_rate_stock_uom`
    is the line's net_rate (after item and document-level discount) divided by
    the conversion factor. `purchase_rate` / `stock_uom_rate` are the list-side
    figures before document-level discount and are kept for reference.

    `rate_company_currency` is what the dialog shows: the cost per stock UOM in
    the company currency. For a receipt it is the line's valuation rate, which
    already includes landed cost; an invoice carries no landed cost, so it is
    the base net rate. `last_selling_rate` is in the company currency too.
    """
    if not frappe.has_permission("Purchase Invoice", "read"):
        frappe.throw("Not permitted", frappe.PermissionError)

    params = {"limit": min(cint(limit) or 20, 200), "item_code": item_code or ""}

    rows = frappe.db.sql("""
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
            pii.net_rate,
            pii.base_net_rate,
            NULL AS valuation_rate,
            pii.conversion_factor,
            pii.amount,
            pi.currency,
            pii.stock_uom_rate
        FROM `tabPurchase Invoice Item` pii
        JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent
        LEFT JOIN `tabSupplier` sup ON sup.name = pi.supplier
        WHERE pi.docstatus = 1
          AND (%(item_code)s = '' OR pii.item_code = %(item_code)s))
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
            pri.net_rate,
            pri.base_net_rate,
            pri.valuation_rate,
            pri.conversion_factor,
            pri.amount,
            pr.currency,
            pri.stock_uom_rate
        FROM `tabPurchase Receipt Item` pri
        JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
        LEFT JOIN `tabSupplier` sup ON sup.name = pr.supplier
        WHERE pr.docstatus = 1
          AND (%(item_code)s = '' OR pri.item_code = %(item_code)s))
        ORDER BY posting_date DESC, doc_name DESC
        LIMIT %(limit)s
    """, params, as_dict=True)

    for r in rows:
        cf = flt(r.get("conversion_factor")) or 1
        net = flt(r.get("net_rate"))
        # net_rate is 0 only on rows that predate it; fall back to the old figure.
        r["net_rate_stock_uom"] = (net / cf) if net else flt(r.get("stock_uom_rate"))
        base_net = flt(r.get("base_net_rate")) / cf
        r["rate_company_currency"] = flt(r.get("valuation_rate")) or base_net
        r["company_currency"] = erpnext.get_company_currency(r.get("company")) if r.get("company") else ""

    item_codes = list({r["item_code"] for r in rows if r.get("item_code")})
    last_selling = _get_last_selling_rates(item_codes)
    for r in rows:
        r["last_selling_rate"] = last_selling.get(r.get("item_code")) or 0

    _add_arabic_names(
        rows,
        party_doctype="Supplier",
        party_key="supplier",
        arabic_party_field="custom_supplier_name_arabic",
    )
    return rows
