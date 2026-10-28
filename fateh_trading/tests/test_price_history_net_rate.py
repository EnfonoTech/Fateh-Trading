import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from fateh_trading.api import get_item_purchase_history, get_item_sales_history


class TestItemPurchaseHistory(FrappeTestCase):
	"""Ticket 7: the history shows the net purchase cost, not the pre-discount rate."""

	def _line_with_document_discount(self):
		rows = frappe.db.sql(
			"""
			select pii.item_code, pi.name as doc_name, pii.rate, pii.net_rate, pii.conversion_factor
			from `tabPurchase Invoice Item` pii
			join `tabPurchase Invoice` pi on pi.name = pii.parent
			where pi.docstatus = 1 and pii.net_rate > 0 and pii.rate - pii.net_rate > 1
			order by pi.posting_date desc
			limit 1
			""",
			as_dict=True,
		)
		return rows[0] if rows else None

	def test_net_rate_is_used_not_the_list_rate(self):
		line = self._line_with_document_discount()
		if not line:
			self.skipTest("no Purchase Invoice line with a document-level discount")

		rows = get_item_purchase_history(item_code=line.item_code, limit=200)
		match = [r for r in rows if r["doc_name"] == line.doc_name]
		self.assertTrue(match, "the discounted invoice must appear in the history")
		row = match[0]

		expected = flt(line.net_rate) / (flt(line.conversion_factor) or 1)
		self.assertAlmostEqual(row["net_rate_stock_uom"], expected, places=4)
		self.assertLess(row["net_rate_stock_uom"], flt(row["stock_uom_rate"]))

	def test_rows_carry_arabic_keys(self):
		code = frappe.db.get_value("Item", {"custom_item_name_arabic": ["!=", ""]}, "name")
		if not code:
			self.skipTest("no item with an Arabic name")
		purchase = get_item_purchase_history(item_code=code, limit=5)
		sales = get_item_sales_history(item_code=code, limit=5)
		for rows in (purchase, sales):
			for r in rows:
				self.assertIn("item_name_arabic", r)
				self.assertIn("party_name_arabic", r)
			if rows:
				self.assertTrue(rows[0]["item_name_arabic"])

	def test_limit_is_capped(self):
		rows = get_item_purchase_history(item_code=None, limit=100000)
		self.assertLessEqual(len(rows), 200)

	def test_receipt_rate_is_company_currency_with_landed_cost(self):
		"""Imports showed `13.50 $`; the dialog must show the SAR cost incl. landed cost."""
		line = frappe.db.sql(
			"""
			select pri.item_code, pr.name as doc_name, pri.valuation_rate
			from `tabPurchase Receipt Item` pri
			join `tabPurchase Receipt` pr on pr.name = pri.parent
			where pr.docstatus = 1 and pri.landed_cost_voucher_amount > 0 and pr.conversion_rate > 1
			order by pr.posting_date desc
			limit 1
			""",
			as_dict=True,
		)
		if not line:
			self.skipTest("no foreign-currency receipt with landed cost")
		line = line[0]

		rows = get_item_purchase_history(item_code=line.item_code, limit=200)
		row = next(r for r in rows if r["doc_name"] == line.doc_name)
		self.assertAlmostEqual(row["rate_company_currency"], flt(line.valuation_rate), places=4)
		self.assertGreater(row["rate_company_currency"], row["net_rate_stock_uom"])
		self.assertNotEqual(row["company_currency"], row["currency"])
